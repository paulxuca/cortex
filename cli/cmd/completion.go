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

package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var completionCmd = &cobra.Command{
	Use:   "completion",
	Short: "generate bash completion scripts",
	Long: `Generate bash completion scripts.

Add this to your bashrc or bash profile:
  source <(cortex completion)
Or run:
  echo 'source <(cortex completion)' >> ~/.bash_profile  # Mac
  echo 'source <(cortex completion)' >> ~/.bashrc  # Linux

Note: This will also add the alias "cx"
`,
	Args: cobra.NoArgs,
	Run: func(cmd *cobra.Command, args []string) {
		rootCmd.GenBashCompletion(os.Stdout)
		aliasText := `
# alias

alias cx='cortex'
if [[ $(type -t compopt) = "builtin" ]]; then
    complete -o default -F __start_cortex cx
else
    complete -o default -o nospace -F __start_cortex cx
fi
`
		fmt.Print(aliasText)
	},
}
