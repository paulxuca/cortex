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


def transform_spark(data, features, args, transformed_feature):
    return data.withColumn(
        transformed_feature, ((data[features["num"]] - args["mean"]) / args["stddev"])
    )


def transform_python(sample, args):
    return (sample["num"] - args["mean"]) / args["stddev"]


def reverse_transform_python(transformed_value, args):
    return args["mean"] + (transformed_value * args["stddev"])
