import os
from dataclasses import replace
from test.application.fixtures import *
from test.application.launchoptions import *
from test.sshfilesystem_assertions import (
    assert_sshfs_connected_with_connection_data,
    assert_sshfs_connected_with_keyfile_from_connection_data,
    assert_sshfs_connected_with_password_from_connection_data)
from test.testdoubles.executor import SlurmJobExecutorFactoryStub
from test.testdoubles.filesystem import sshfs_with_connection_fake
from test.testdoubles.sshclient import ProxyJumpVerifyingSSHClient
from unittest.mock import ANY, MagicMock, Mock, call

import pytest
from hpcrocket.core.application import Application
from hpcrocket.core.environmentpreparation import CopyInstruction
from hpcrocket.core.launchoptions import LaunchOptions
from hpcrocket.pyfilesystem.factory import PyFilesystemFactory
from hpcrocket.ssh.connectiondata import ConnectionData
from hpcrocket.ssh.errors import SSHError


@pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_valid_config__when_running__should_open_local_fs_in_current_directory(osfs_type_mock):
    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options()), Mock())

    sut.run(options())

    osfs_type_mock.assert_called_with(".")


@pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_valid_config__when_running__should_login_to_sshfs_with_correct_credentials(sshfs_type_mock):
    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options()), Mock())

    sut.run(options())

    assert_sshfs_connected_with_connection_data(sshfs_type_mock, main_connection())


@pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_ssh_connection_not_available_for_sshfs__when_running__should_log_error_and_exit(sshfs_type_mock):
    sshfs_type_mock.side_effect = SSHError(main_connection().hostname)

    ui_spy = Mock()
    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options()), ui_spy)

    sut.run(options())

    ui_spy.error.assert_called_once_with(f"SSHError: {main_connection().hostname}")


@pytest.mark.usefixtures("successful_sshclient_stub")
@pytest.mark.parametrize(["input_keyfile", "expected_keyfile"], INPUT_AND_EXPECTED_KEYFILE_PATHS)
def test__given_config_with_only_private_keyfile__when_running__should_login_to_sshfs_with_correct_credentials(
        sshfs_type_mock, input_keyfile, expected_keyfile):

    os.environ['HOME'] = HOME_DIR
    valid_options = LaunchOptions(
        connection=ConnectionData(
            hostname="example.com",
            username="myuser",
            keyfile=input_keyfile),
        sbatch="test.job",
        poll_interval=0
    )

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(valid_options), Mock())

    sut.run(valid_options)

    connection_with_resolved_keyfile = replace(valid_options.connection, keyfile=expected_keyfile)
    assert_sshfs_connected_with_keyfile_from_connection_data(sshfs_type_mock, connection_with_resolved_keyfile)


@pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_config_with_only_password__when_running__should_login_to_sshfs_with_correct_credentials(sshfs_type_mock):
    valid_options = LaunchOptions(
        connection=ConnectionData(
            hostname="example.com",
            username="myuser",
            password="mypassword"),
        sbatch="test.job",
        poll_interval=0
    )

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(valid_options), Mock())

    sut.run(valid_options)

    assert_sshfs_connected_with_password_from_connection_data(sshfs_type_mock, valid_options.connection)


def test__given_config_with_proxy__when_running__should_login_to_sshfs_over_proxy(sshclient_type_mock):
    # NOTE: We're using only password authentication here, because SSHFS combines key and keyfile into a single option
    #       so we cannot compare against connection data with keyfile AND key as SSHFS will only be called with one of them.

    mock = ProxyJumpVerifyingSSHClient(main_connection_only_password(), [proxy_connection_only_password()])
    sshclient_type_mock.return_value = mock

    with sshfs_with_connection_fake(sshclient_type_mock.return_value):
        sut = Application(
            SlurmJobExecutorFactoryStub(),
            PyFilesystemFactory(options_with_proxy_only_password()),
            Mock())

        sut.run(options_with_proxy_only_password())

        mock.verify()


@pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_config__when_running__should_open_sshfs_in_home_dir(sshfs_type_mock: MagicMock):
    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options()), Mock())

    sut.run(options())

    sshfs_mock: MagicMock = sshfs_type_mock.return_value
    calls = sshfs_mock.mock_calls

    assert call.opendir(HOME_DIR, factory=ANY) in calls


@ pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_config_with_files_to_copy__when_running__should_copy_files_to_remote_filesystem(osfs_type_mock,
                                                                                                sshfs_type_mock):
    options = options_with_files_to_copy([
        CopyInstruction("myfile.txt", "mycopy.txt"),
        CopyInstruction("otherfile.gif", "copy.gif")
    ])

    osfs_type_mock.create("myfile.txt")
    osfs_type_mock.create("otherfile.gif")

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options), Mock())

    sut.run(options)

    assert sshfs_type_mock.exists(f"{HOME_DIR}/mycopy.txt")
    assert sshfs_type_mock.exists(f"{HOME_DIR}/copy.gif")


@ pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_config_with_files_to_clean__when_running__should_remove_files_from_remote_filesystem(osfs_type_mock,
                                                                                                     sshfs_type_mock):
    options = options_with_files_to_copy_and_clean(
        [CopyInstruction("myfile.txt", "mycopy.txt")],
        ["mycopy.txt"]
    )

    osfs_type_mock.return_value.create("myfile.txt")

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options), Mock())

    sut.run(options)

    assert not sshfs_type_mock.return_value.exists(f"{HOME_DIR}/mycopy.txt")


@ pytest.mark.usefixtures("successful_sshclient_stub")
def test__given_config_with_files_to_collect__when_running__should_collect_files_from_remote_filesystem_after_completing_job_and_before_cleaning(osfs_type_mock,
                                                                                                                                                 sshfs_type_mock):
    options = options_with_files_to_copy_collect_and_clean(
        files_to_copy=[CopyInstruction("myfile.txt", "mycopy.txt")],
        files_to_clean=["mycopy.txt"],
        files_to_collect=[CopyInstruction("mycopy.txt", "mycopy.txt")]
    )

    local_fs = osfs_type_mock.return_value
    local_fs.create("myfile.txt")

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options), Mock())

    sut.run(options)

    sshfs = sshfs_type_mock.return_value
    assert local_fs.exists("mycopy.txt")
    assert not sshfs.exists("mycopy.txt")


@ pytest.mark.usefixtures("sshclient_type_mock")
def test__given_config_with_non_existing_file_to_copy__when_running__should_perform_rollback_and_exit(osfs_type_mock,
                                                                                                      sshfs_type_mock):
    options = options_with_files_to_copy([
        CopyInstruction("myfile.txt", "mycopy.txt"),
        CopyInstruction("otherfile.gif", "copy.gif")
    ])

    osfs_type_mock.return_value.create("myfile.txt")

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options), Mock())

    exit_code = sut.run(options)

    assert not sshfs_type_mock.return_value.exists(f"{HOME_DIR}/mycopy.txt")
    assert not sshfs_type_mock.return_value.exists(f"{HOME_DIR}/copy.gif")
    assert exit_code == 1


@ pytest.mark.usefixtures("sshclient_type_mock", "sshfs_type_mock")
def test__given_config_with_non_existing_file_to_copy__when_running__should_print_to_ui(osfs_type_mock):

    options = options_with_files_to_copy([
        CopyInstruction("myfile.txt", "mycopy.txt"),
        CopyInstruction("otherfile.gif", "copy.gif")
    ])

    osfs_type_mock.return_value.create("myfile.txt")

    ui_spy = Mock()
    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options), ui_spy)

    sut.run(options)

    assert call.error(
        "FileNotFoundError: otherfile.gif") in ui_spy.method_calls


@ pytest.mark.usefixtures("sshclient_type_mock")
def test__given_config_with_already_existing_file_to_copy__when_running__should_perform_rollback_and_exit(
        osfs_type_mock, sshfs_type_mock):
    options = options_with_files_to_copy([
        CopyInstruction("myfile.txt", "mycopy.txt"),
        CopyInstruction("otherfile.gif", "copy.gif")
    ])

    osfs_type_mock.return_value.create("myfile.txt")
    osfs_type_mock.return_value.create("otherfile.gif")

    sshfs_type_mock.return_value.create(f"{HOME_DIR}/copy.gif")

    sut = Application(SlurmJobExecutorFactoryStub(), PyFilesystemFactory(options), Mock())

    exit_code = sut.run(options)

    assert not sshfs_type_mock.return_value.exists(f"{HOME_DIR}/mycopy.txt")
    assert sshfs_type_mock.return_value.exists(f"{HOME_DIR}/copy.gif")
    assert exit_code == 1
