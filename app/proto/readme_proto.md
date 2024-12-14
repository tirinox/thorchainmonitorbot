
# How to generate Protobuf interface for Python.
We are going to use Betterproto library because it is modern and cool.
https://github.com/danielgtaylor/python-betterproto

## Install both the library and compiler
`pip install "betterproto[compiler]"`

## Install just the library (to use the generated code output)
`pip install betterproto`

Download Cosmos SDK (AFAIK THORChain uses v0.50.x, check it):
```
git clone https://github.com/cosmos/cosmos-sdk.git
cd cosmos-sdk
git checkout v0.50.10
cd ..
```


Download THORChain source code (https://gitlab.com/thorchain/thornode/) and switch your working directory:
```
git clone https://gitlab.com/thorchain/thornode.git
cd thornode
git checkout release-3.0.0
```


Note: use the "release-vxxx" branch. For instance: https://gitlab.com/thorchain/thornode/-/tree/release-1.123.0

Command to generate Python files:
```mkdir -p pylib
python -m pip install grpcio
python -m pip install grpcio-tools
python -m grpc_tools.protoc -I "proto" -I "third_party/proto" -I "../cosmos-sdk/proto" --python_betterproto_out=pylib proto/thorchain/v1/x/thorchain/types/*.proto "../cosmos-sdk/proto/cosmos/tx/v1beta1/tx.proto"
```

Now move the contents of "pylib" here.

### Troubleshooting:
If you have errors concerning "safe_unicode" imports, just downgrade your library:
`pip install markupsafe==2.0.1`
