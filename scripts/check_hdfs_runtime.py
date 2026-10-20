"""Check PyArrow/libhdfs/JVM file I/O without contacting an HDFS cluster."""

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from pyarrow.fs import HadoopFileSystem


def main() -> None:
    """Exercise the Hadoop client through JNI using its local filesystem."""
    config = Path(os.environ["HADOOP_CONF_DIR"])
    for name in ("core-site.xml", "hdfs-site.xml", "hadoop-policy.xml"):
        assert ElementTree.parse(config / name).getroot().tag == "configuration"
    for name in ("hadoop-env.sh", "hadoop-metrics2.properties", "log4j.properties"):
        assert (config / name).is_file(), f"Missing Hadoop configuration: {name}"
    filesystem = HadoopFileSystem(
        "default", port=0, extra_conf={"fs.defaultFS": "file:///"}
    )
    with TemporaryDirectory() as directory:
        path = Path(directory) / "sample.jsonl"
        content = '{"text":"HDFS runtime 확인"}\n'.encode()
        path.write_bytes(content)
        info = filesystem.get_file_info(str(path))
        assert info.size == len(content), "Hadoop file metadata mismatch"
        with filesystem.open_input_stream(str(path)) as stream:
            assert stream.read() == content, "Hadoop file content mismatch"
        listing = subprocess.run(
            ["hdfs", "dfs", "-fs", "file:///", "-ls", directory],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert str(path) in listing.stdout, "HDFS CLI file listing mismatch"
    print("PyArrow, libhdfs and JVM file I/O: OK (local filesystem only)")
    print("hdfs dfs -ls: OK (local filesystem only)")
    print("Standard Hadoop configuration files: OK")


if __name__ == "__main__":
    main()
