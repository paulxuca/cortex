# Copyright 2019 Cortex Labs, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import argparse
import json
import traceback

from pyspark.sql import SparkSession

from lib import util
from lib.context import Context
from lib.log import get_logger
from lib.exceptions import UserException, CortexException, UserRuntimeException
import spark_util
import pyspark.sql.functions as F


logger = get_logger()


def show_df(df, ctx, n=3, sort=True):
    if df and ctx:  # and not ctx.cortex_config["hide_data_in_logs"]:
        col_order = df.columns
        if sort:
            col_order = sorted(col_order)
        samples = [sample.asDict() for sample in df.head(n)]
        util.print_samples_horiz(
            samples, sep="", first_sep=":", pad=4, first_pad=2, key_list=col_order
        )


def show_aggregates(ctx, aggregates, truncate=80):
    logger.info("Aggregates:")

    # duplicate the results for resources with different names but same ids for UI purposes
    for key, value in list(aggregates.items()):
        id = ctx.ag_id_map.name_map[key]["id"]
        for name in ctx.ag_id_map[id]["aliases"]:
            aggregates[name] = value

    max_name_len = max([len(name) for name in aggregates.keys()])

    for name in sorted(aggregates):
        result = aggregates[name]
        name_padded = util.pad_right(name + ":", max_name_len + 3)
        logger.info(name_padded + util.truncate_str(json.dumps(result), truncate))


def get_spark_session(app_name):
    return SparkSession.builder.appName(app_name).getOrCreate()


def parse_args(args):
    should_ingest = args.ingest

    features_to_validate = []
    if args.raw_features != None and args.raw_features != "":
        features_to_validate = sorted(args.raw_features.split(","))

    features_to_aggregate = []
    if args.aggregates != None and args.aggregates != "":
        features_to_aggregate = sorted(args.aggregates.split(","))

    features_to_transform = []
    if args.transformed_features != None and args.transformed_features != "":
        features_to_transform = sorted(args.transformed_features.split(","))

    training_datasets = []
    if args.training_datasets != None and args.training_datasets != "":
        training_datasets = sorted(args.training_datasets.split(","))

    return (
        should_ingest,
        features_to_validate,
        features_to_aggregate,
        features_to_transform,
        training_datasets,
    )


def ingest_raw_dataset(spark, ctx, features_to_validate, should_ingest):
    if should_ingest:
        features_to_validate = list(ctx.rf_id_map.keys())

    if len(features_to_validate) > 0:
        feature_resources_to_validate = [ctx.rf_id_map[f] for f in features_to_validate]
        ctx.upload_resource_status_start(*feature_resources_to_validate)
        try:
            if should_ingest:
                logger.info("Ingesting")
                logger.info(
                    "Ingesting {} data from {}".format(
                        ctx.app["name"], ctx.environment["data"]["path"]
                    )
                )
                ingest_df = spark_util.ingest(ctx, spark)
                full_dataset_counter = ingest_df.count()
                if ctx.environment["data"].get("drop_null"):
                    ingest_df = ingest_df.dropna()
                    logger.info("Dropping any rows that contain null values")
                    write_dataset_counter = ingest_df.count()

                logger.info(
                    "Caching {} data (version: {})".format(ctx.app["name"], ctx.dataset_version)
                )
                spark_util.write_raw_dataset(ingest_df, ctx)

                if ctx.environment["data"].get("drop_null"):
                    logger.info(
                        "{} rows read, {} rows dropped, {} rows ingested".format(
                            full_dataset_counter,
                            full_dataset_counter - write_dataset_counter,
                            write_dataset_counter,
                        )
                    )
                else:
                    logger.info("{} rows ingested".format(full_dataset_counter))
            logger.info(
                "Reading {} data (version: {})".format(ctx.app["name"], ctx.dataset_version)
            )
            raw_df = spark_util.read_raw_dataset(ctx, spark)
            total_row_count = raw_df.count()
            conditions_dict = spark_util.value_check_data(ctx, raw_df, features_to_validate)

            if len(conditions_dict) > 0:
                for column, cond_count_list in conditions_dict.items():
                    for condition, fail_count in cond_count_list:
                        logger.error(
                            "Data validation {} has been violated in {}/{} samples".format(
                                condition, fail_count, total_row_count
                            )
                        )
                raise UserException("raw feature validations failed")
        except:
            ctx.upload_resource_status_failed(*feature_resources_to_validate)
            raise
        ctx.upload_resource_status_success(*feature_resources_to_validate)
        logger.info("First {} samples:".format(3))
        show_df(raw_df, ctx, 3)
    else:
        logger.info("Reading {} data (version: {})".format(ctx.app["name"], ctx.dataset_version))
        raw_df = spark_util.read_raw_dataset(ctx, spark)
        spark_util.value_check_data(ctx, raw_df, features_to_validate)

    return raw_df


def run_custom_aggregators(spark, ctx, features_to_aggregate, raw_df):
    logger.info("Aggregating")
    results = {}

    aggregate_names = [ctx.ag_id_map[f]["name"] for f in features_to_aggregate]

    builtin_aggregates, custom_aggregates = spark_util.split_aggregators(
        sorted(aggregate_names), ctx
    )

    if len(builtin_aggregates) > 0:
        ctx.upload_resource_status_start(*builtin_aggregates)
        try:
            for aggregate in builtin_aggregates:
                logger.info("Aggregating " + ", ".join(ctx.ag_id_map[aggregate["id"]]["aliases"]))

            results = spark_util.run_builtin_aggregators(builtin_aggregates, raw_df, ctx, spark)
        except:
            ctx.upload_resource_status_failed(*builtin_aggregates)
            raise
        ctx.upload_resource_status_success(*builtin_aggregates)

    for aggregate in custom_aggregates:
        ctx.upload_resource_status_start(aggregate)
        try:
            logger.info("Aggregating " + ", ".join(ctx.ag_id_map[aggregate["id"]]["aliases"]))
            result = spark_util.run_custom_aggregator(aggregate, raw_df, ctx, spark)
            results[aggregate["name"]] = result
        except:
            ctx.upload_resource_status_failed(aggregate)
            raise
        ctx.upload_resource_status_success(aggregate)

    show_aggregates(ctx, results)


def validate_transformers(spark, ctx, features_to_transform, raw_df):
    logger.info("Validating Transformers")

    TEST_DF_SIZE = 100

    logger.info("Sanity checking transformers against the first {} samples".format(TEST_DF_SIZE))
    sample_df = raw_df.limit(TEST_DF_SIZE).cache()
    test_df = raw_df.limit(TEST_DF_SIZE).cache()

    resource_list = sorted(
        [ctx.tf_id_map[f] for f in features_to_transform], key=lambda r: r["name"]
    )
    for transformed_feature in resource_list:
        ctx.upload_resource_status_start(transformed_feature)
        try:
            input_features_dict = transformed_feature["inputs"]["features"]

            input_cols = []

            for k in sorted(input_features_dict.keys()):
                if util.is_list(input_features_dict[k]):
                    input_cols += sorted(input_features_dict[k])
                else:
                    input_cols.append(input_features_dict[k])

            tf_name = transformed_feature["name"]
            logger.info("Transforming {} to {}".format(", ".join(input_cols), tf_name))

            spark_util.validate_transformer(tf_name, test_df, ctx, spark)
            sample_df = spark_util.transform_feature(
                transformed_feature["name"], sample_df, ctx, spark
            )

            sample_df.select(tf_name).collect()  # run the transformer
            show_df(sample_df.select(*input_cols, tf_name), ctx, n=3, sort=False)

            for alias in transformed_feature["aliases"][1:]:
                logger.info("Transforming {} to {}".format(", ".join(input_cols), alias))

                display_transform_df = sample_df.withColumn(alias, F.col(tf_name)).select(
                    *input_cols, alias
                )
                show_df(display_transform_df, ctx, n=3, sort=False)
        except:
            ctx.upload_resource_status_failed(transformed_feature)
            raise
        ctx.upload_resource_status_success(transformed_feature)


def create_training_datasets(spark, ctx, training_datasets, accumulated_df):
    unique_training_datasets = [ctx.td_id_map[td_id] for td_id in training_datasets]

    if len(unique_training_datasets) > 0:
        logger.info("Generating Training Datasets")

    for td_resource in sorted(unique_training_datasets, key=lambda r: r["name"]):
        ctx.upload_resource_status_start(td_resource)
        try:
            accumulated_df = spark_util.transform(
                td_resource["model_name"], accumulated_df, ctx, spark
            )
            logger.info("Generating {}".format(", ".join(td_resource["aliases"])))
            spark_util.write_training_data(td_resource["model_name"], accumulated_df, ctx)
        except:
            ctx.upload_resource_status_failed(td_resource)
            raise
        ctx.upload_resource_status_success(td_resource)


def run_job(args):
    should_ingest, features_to_validate, features_to_aggregate, features_to_transform, training_datasets = parse_args(
        args
    )

    resource_id_list = (
        features_to_validate + features_to_aggregate + features_to_transform + training_datasets
    )

    try:
        ctx = Context(s3_path=args.context, cache_dir=args.cache_dir, workload_id=args.workload_id)
    except Exception as e:
        logger.exception("An error occurred, see the logs for more details.")
        sys.exit(1)

    try:
        spark = None  # For the finally clause
        spark = get_spark_session(ctx.workload_id)
        raw_df = ingest_raw_dataset(spark, ctx, features_to_validate, should_ingest)

        if len(features_to_aggregate) > 0:
            run_custom_aggregators(spark, ctx, features_to_aggregate, raw_df)

        if len(features_to_transform) > 0:
            validate_transformers(spark, ctx, features_to_transform, raw_df)

        create_training_datasets(spark, ctx, training_datasets, raw_df)

        util.log_job_finished(ctx.workload_id)
    except CortexException as e:
        e.wrap("error")
        logger.error(str(e))
        logger.exception(
            "An error occurred, see `cx logs {} {}` for more details.".format(
                ctx.id_map[resource_id_list[0]]["resource_type"],
                ctx.id_map[resource_id_list[0]]["name"],
            )
        )
        sys.exit(1)
    except Exception as e:
        logger.exception(
            "An error occurred, see `cx logs {} {}` for more details.".format(
                ctx.id_map[resource_id_list[0]]["resource_type"],
                ctx.id_map[resource_id_list[0]]["name"],
            )
        )
        sys.exit(1)
    finally:
        if spark is not None:
            spark.stop()


def main():
    logger.info("Starting")
    parser = argparse.ArgumentParser()

    na = parser.add_argument_group("required named arguments")
    na.add_argument("--workload-id", required=True, help="Workload ID")
    na.add_argument(
        "--context",
        required=True,
        help="S3 path to context (e.g. s3://bucket/path/to/context.json)",
    )
    na.add_argument("--cache-dir", required=True, help="Local path for the context cache")

    na = parser.add_argument_group("optional named arguments")
    na.add_argument(
        "--ingest", required=False, action="store_true", help="Should external dataset be ingested"
    )
    na.add_argument(
        "--raw-features",
        required=False,
        help="Comma separated resource ids of raw features to validate",
    )
    na.add_argument(
        "--aggregates", required=False, help="Comma separated resource ids of aggregates to run"
    )
    na.add_argument(
        "--transformed-features",
        required=False,
        help="Comma separated resource ids of features to transform",
    )
    na.add_argument(
        "--training-datasets",
        required=False,
        help="Comma separated resource ids of training dataset to create",
    )

    parser.set_defaults(func=run_job)

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit()

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
