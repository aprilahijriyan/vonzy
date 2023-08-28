# Demo Workflow

The following is a sample workflow demonstrating the `vonzy` features.

* `helloworld.yml`: An example of a workflow that prints the words 'Hello' and 'World' in steps. Also, prints the result of the 'step' itself.
* `rsync.yml`: An example of a workflow that uploads a project with rsync and run a python script using SSH.

## Usage

To run a workflow. Just pass the workflow file to the `-c` option in the `vonzy` command.
Example:

```sh
vonzy -c helloworld.yml run
```
