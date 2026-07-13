## Workflow Artifact Delivery

Write the complete state artifact to `{{OUTPUT_PATH}}` using `write_file`.

This exact path is owned by the workflow. Do not write this state artifact anywhere else.

After the file is complete, the final response may be a short confirmation. If `write_file` cannot be used, return the complete artifact as the final response.
