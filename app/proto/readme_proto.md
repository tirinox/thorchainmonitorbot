
# How to generate Protobuf interface for Python.
We are going to use Betterproto library because it is modern and cool.
https://github.com/danielgtaylor/python-betterproto

## Install both the library and compiler
`pip install "betterproto[compiler]"`

## Install just the library (to use the generated code output)
`pip install betterproto`

Download THORChain source code (https://gitlab.com/thorchain/thornode/) and switch your working directory:
`cd ~/Downloads/thornode-master`
Note: use the "release-vxxx" branch. For instance: https://gitlab.com/thorchain/thornode/-/tree/release-1.95.0

Command to generate Python files:
```mkdir -p pylib
python -m pip install grpcio
python -m pip install grpcio-tools
python -m grpc_tools.protoc -I "proto" -I "third_party/proto" --python_betterproto_out=pylib proto/thorchain/v1/x/thorchain/types/*.proto```

Under the "pylib" directory you will find "types.py", move it here and rename to "thor_types.py" 

### Troubleshooting:
If you have errors concerning "safe_unicode" imports, just downgrade your library:
`pip install markupsafe==2.0.1`
