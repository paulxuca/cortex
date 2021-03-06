/*
Copyright 2019 Cortex Labs, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package userconfig

import (
	"github.com/cortexlabs/cortex/pkg/api/resource"
	cr "github.com/cortexlabs/cortex/pkg/utils/configreader"
	"github.com/cortexlabs/cortex/pkg/utils/util"
)

type Transformers []*Transformer

type Transformer struct {
	Name       string  `json:"name"  yaml:"name"`
	Inputs     *Inputs `json:"inputs"  yaml:"inputs"`
	OutputType string  `json:"output_type"  yaml:"output_type"`
	Path       string  `json:"path"  yaml:"path"`
}

var transformerValidation = &cr.StructValidation{
	StructFieldValidations: []*cr.StructFieldValidation{
		&cr.StructFieldValidation{
			StructField: "Name",
			StringValidation: &cr.StringValidation{
				Required:                   true,
				AlphaNumericDashUnderscore: true,
			},
		},
		&cr.StructFieldValidation{
			StructField:      "Path",
			StringValidation: &cr.StringValidation{},
			DefaultField:     "Name",
			DefaultFieldFunc: func(name interface{}) interface{} {
				return "implementations/transformers/" + name.(string) + ".py"
			},
		},
		&cr.StructFieldValidation{
			StructField: "OutputType",
			StringValidation: &cr.StringValidation{
				Required:      true,
				AllowedValues: FeatureTypeStrings(),
			},
		},
		inputTypesFieldValidation,
		typeFieldValidation,
	},
}

func (transformers Transformers) Validate() error {
	dups := util.FindDuplicateStrs(transformers.Names())
	if len(dups) > 0 {
		return ErrorDuplicateConfigName(dups[0], resource.TransformerType)
	}
	return nil
}

func (transformers Transformers) Get(name string) *Transformer {
	for _, transformer := range transformers {
		if transformer.Name == name {
			return transformer
		}
	}
	return nil
}

func (transformer *Transformer) GetName() string {
	return transformer.Name
}

func (transformer *Transformer) GetResourceType() resource.Type {
	return resource.TransformerType
}

func (transformers Transformers) Names() []string {
	names := make([]string, len(transformers))
	for i, transformer := range transformers {
		names[i] = transformer.Name
	}
	return names
}
