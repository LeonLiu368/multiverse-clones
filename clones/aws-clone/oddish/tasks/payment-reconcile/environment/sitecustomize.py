# Auto-loaded by CPython's site machinery when this directory (/opt/awscli) is on sys.path.
# It installs the aws-clone IAM hybrid shim into botocore for both the `aws`/`awslocal` CLIs and any
# agent that imports boto3/botocore from /opt/awscli. Failure here must never break the interpreter.
try:
    import aws_clone_shim

    aws_clone_shim.install()
except Exception:
    pass
