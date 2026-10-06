# SPDX-License-Identifier: GPL-2.0

import os
import unittest
from unittest import mock

from podman_compose import container_to_build_args
from podman_compose import normalize_service


def create_compose_mock(project_name="test_project_name"):
    compose = mock.Mock()
    compose.project_name = project_name
    compose.dirname = "test_dirname"
    compose.container_names_by_service.get = mock.Mock(return_value=None)
    compose.prefer_volume_over_mount = False
    compose.default_net = None
    compose.networks = {}
    compose.x_podman = {}
    return compose


def get_minimal_container():
    return {
        "name": "project_name_service_name1",
        "service_name": "service_name",
        "image": "new-image",
        "build": {},
    }


def get_minimal_args():
    args = mock.Mock()
    args.build_arg = []
    args.pull = None
    return args


class TestTicketvectorBuildContext(unittest.TestCase):
    def test_containerfile_in_build_context(self):
        compose = create_compose_mock()
        container = get_minimal_container()
        container["build"]["context"] = "./subdir"

        got = container_to_build_args(compose, container, get_minimal_args(), lambda path: True)

        self.assertEqual(
            got,
            [
                "-f",
                "subdir/Containerfile",
                "-t",
                "new-image",
                "--no-cache",
                "./subdir",
            ],
        )

    def test_subdir_prefixes_relative_string_volumes(self):
        got = normalize_service(
            {"volumes": ["./nested/relative:/mnt", "../dir-in-parent:/mnt", "..:/mnt", ".:/mnt"]},
            sub_dir="./sub_dir",
        )

        self.assertEqual(len(got["volumes"]), 4)
        for got_volume, expected_volume in zip(
            got["volumes"],
            [
                "./sub_dir/./nested/relative:/mnt",
                "./sub_dir/../dir-in-parent:/mnt",
                "./sub_dir/..:/mnt",
                "./sub_dir/.:/mnt",
            ],
            strict=True,
        ):
            got_source, got_target = got_volume.split(":", 1)
            expected_source, expected_target = expected_volume.split(":", 1)
            self.assertEqual(os.path.normpath(got_source), os.path.normpath(expected_source))
            self.assertEqual(got_target, expected_target)

    def test_subdir_prefixes_relative_bind_volume_sources(self):
        got = normalize_service(
            {
                "volumes": [
                    {
                        "type": "bind",
                        "source": "./nested/relative",
                        "target": "/mnt",
                    }
                ]
            },
            sub_dir="./sub_dir",
        )

        self.assertEqual(len(got["volumes"]), 1)
        got_volume = got["volumes"][0]
        self.assertEqual(got_volume["type"], "bind")
        self.assertEqual(os.path.normpath(got_volume["source"]), os.path.normpath("./sub_dir/./nested/relative"))
        self.assertEqual(got_volume["target"], "/mnt")


if __name__ == "__main__":
    unittest.main()
