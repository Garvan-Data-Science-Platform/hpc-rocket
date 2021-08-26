from test.pyfilesystem_testdoubles import PyFilesystemStub, VerifyDirsCreatedAndCopyPyFSMock
from unittest.mock import MagicMock, patch

import fs
import fs.base
import pytest
from fs import ResourceType
from ssh_slurm_runner.filesystem import Filesystem
from ssh_slurm_runner.pyfilesystem import PyFilesystemBased


# This class name starts with an underscore because pytest tries to collect it as test otherwise
class _TestFilesystemImpl(PyFilesystemBased):

    def __init__(self, fs_mock) -> None:
        super().__init__()
        self._internal_fs = fs_mock

    @property
    def internal_fs(self) -> fs.base.FS:
        return self._internal_fs


class FilesystemStub(PyFilesystemBased):

    def __init__(self, internal_fs=None) -> None:
        self._internal_fs = internal_fs or MagicMock(
            spec=fs.base.FS).return_value
        self.existing_files = set()
        self.existing_dirs = set()

    @property
    def internal_fs(self) -> fs.base.FS:
        return self._internal_fs

    def copy(self, source: str, target: str, filesystem: 'Filesystem') -> None:
        pass

    def delete(self, path: str) -> None:
        pass

    def exists(self, path: str) -> None:
        return path in self.existing_files or path in self.existing_dirs


class NonPyFilesystemBasedFilesystem(Filesystem):

    def __init__(self) -> None:
        pass

    def copy(self, source: str, target: str, filesystem: 'Filesystem') -> None:
        pass

    def delete(self, path: str) -> None:
        pass

    def exists(self, path: str) -> None:
        pass


SOURCE = "~/file.txt"
TARGET = "~/another/folder/copy.txt"


@pytest.fixture
def fs_type_mock():
    patcher = patch("fs.base.FS")
    type_mock = patcher.start()
    type_mock.return_value.configure_mock(
        exists=exists_with_files(SOURCE),
        isdir=lambda _: False
    )

    yield type_mock

    patcher.stop()


@pytest.fixture
def copy_file():
    patcher = patch("fs.copy.copy_file")

    yield patcher.start()

    patcher.stop()


@pytest.fixture
def copy_dir():
    patcher = patch("fs.copy.copy_dir")

    yield patcher.start()

    patcher.stop()


def test__when_copying_file__should_call_copy_on_fs(fs_type_mock):
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.copy(SOURCE, TARGET)

    sshfs_mock = fs_type_mock.return_value
    sshfs_mock.copy.assert_called_with(SOURCE, TARGET)


def test__when_copying_file__but_parent_dir_missing__should_create_missing_dirs(fs_type_mock):
    target_parent_dir = "~/another/folder"
    mock = VerifyDirsCreatedAndCopyPyFSMock(
        expected_copies=[(SOURCE, TARGET)],
        expected_dirs=[target_parent_dir],
        existing_files=[SOURCE],
        expected_calls=["makedirs", "copy"]
    )

    fs_type_mock.return_value = mock
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.copy(SOURCE, TARGET)

    mock.verify()


def test__when_copying_directory__should_call_copydir_on_fs(fs_type_mock):
    src_dir = "~/mydir"
    copy_dir = "~/copydir"
    sshfs_mock = fs_mock_copy_expecting_directory(fs_type_mock, src_dir)

    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.copy(src_dir, copy_dir)

    sshfs_mock.copydir.assert_called_with(src_dir, copy_dir, create=True)


def test__when_copying_file_to_other_filesystem__should_call_copy_file(fs_type_mock, copy_file):
    fs_mock = FilesystemStub()
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.copy(SOURCE, TARGET, filesystem=fs_mock)

    sshfs_mock = fs_type_mock.return_value
    copy_file.assert_called_with(
        sshfs_mock, SOURCE, fs_mock.internal_fs, TARGET)


def test__when_copying_file_to_other_filesystem__but_parent_dir_missing__should_create_missing_dirs(fs_type_mock, copy_file):
    target_parent_dir = "~/another/folder"
    missing_dirs_mock = VerifyDirsCreatedAndCopyPyFSMock(
        expected_dirs=[target_parent_dir],
        expected_copies=[],
        expected_calls=["makedirs"]
    )

    fs_mock = FilesystemStub(missing_dirs_mock)
    fs_mock.existing_files = [SOURCE]

    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.copy(SOURCE, TARGET, filesystem=fs_mock)

    missing_dirs_mock.verify()
    sshfs_mock = fs_type_mock.return_value
    copy_file.assert_called_with(
        sshfs_mock, SOURCE, fs_mock.internal_fs, TARGET)


@pytest.mark.usefixtures("copy_file")
def test__when_copying_file_to_other_filesystem__and_parent_dir_exists__should_not_try_to_create_dirs(fs_type_mock):
    target_parent_dir = "~/another/folder"

    filesystem_stub = FilesystemStub()
    filesystem_stub.existing_files = [SOURCE]
    filesystem_stub.existing_dirs = [target_parent_dir]

    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.copy(SOURCE, TARGET, filesystem=filesystem_stub)

    filesystem_stub.internal_fs.makedirs.assert_not_called()


def test__when_copying__but_source_does_not_exist__should_raise_file_not_found_error(fs_type_mock):
    fs_type_mock.return_value.configure_mock(exists=exists_with_files())
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    with pytest.raises(FileNotFoundError):
        sut.copy(SOURCE, TARGET)


def test__when_copying__but_file_exists__should_raise_file_exists_error(fs_type_mock):
    fs_type_mock.return_value.configure_mock(
        exists=exists_with_files(SOURCE, TARGET))

    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    with pytest.raises(FileExistsError):
        sut.copy(SOURCE, TARGET)


def test__when_copying_to_other_filesystem__but_file_exists__should_raise_file_exists_error(fs_type_mock, copy_file):
    fs_mock = FilesystemStub()
    fs_mock.existing_files.add(TARGET)
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    with pytest.raises(FileExistsError):
        sut.copy(SOURCE, TARGET, filesystem=fs_mock)


def test__when_copying_directory_to_other_filesystem__should_call_copy_dir(fs_type_mock, copy_dir):
    source_pyfs_mock = fs_type_mock.return_value
    source_pyfs_mock.configure_mock(
        isdir=lambda path: True,
        exists=lambda path: True)

    target_fs_mock = FilesystemStub()
    sut = _TestFilesystemImpl(source_pyfs_mock)

    source = "~/mydir"
    target = "~/copydir"

    sut.copy(source, target, filesystem=target_fs_mock)

    copy_dir.assert_called_with(
        source_pyfs_mock, source,
        target_fs_mock.internal_fs, target)


def test__when_copying_to_non_pyfilesystem__should_raise_runtime_error(fs_type_mock):
    fs_mock = NonPyFilesystemBasedFilesystem()
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    with pytest.raises(RuntimeError):
        sut.copy(SOURCE, TARGET, filesystem=fs_mock)


def test__when_deleting_file__should_call_fs_remove(fs_type_mock):
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.delete(SOURCE)

    sshfs_mock = fs_type_mock.return_value
    sshfs_mock.remove.assert_called_with(SOURCE)


def test__when_deleting_directory__should_call_fs_removetree(fs_type_mock):
    dir_path = "~/mydir"
    sshfs_mock = sshfs_mock_remove_expecting_directory(
        fs_type_mock, dir_path)

    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    sut.delete(dir_path)

    sshfs_mock.removetree.assert_called_with(dir_path)


def test__when_deleting_file_but_does_not_exist__should_raise_file_not_found_error(fs_type_mock):
    fs_type_mock.return_value.configure_mock(exists=exists_with_files())
    sut = _TestFilesystemImpl(fs_type_mock.return_value)

    with pytest.raises(FileNotFoundError):
        sut.delete(SOURCE)


def fs_mock_copy_expecting_directory(fs_type_mock, src_dir):
    sshfs_mock = fs_type_mock.return_value

    def copy(src, dst):
        import fs.errors
        raise fs.errors.FileExpected(src)

    sshfs_mock.configure_mock(
        exists=exists_with_files(src_dir),
        gettype=lambda _: ResourceType.directory,
        isdir=lambda _: True,
        copy=copy
    )

    return sshfs_mock


def sshfs_mock_remove_expecting_directory(fs_type_mock, dir_path):
    sshfs_mock = fs_type_mock.return_value

    def remove(path):
        import fs.errors
        raise fs.errors.FileExpected(path)

    sshfs_mock.configure_mock(
        exists=exists_with_files(dir_path),
        gettype=lambda _: ResourceType.directory,
        isdir=lambda _: True,
        remove=remove
    )

    return sshfs_mock


def exists_with_files(*args):
    def exists(path: str):
        return path in args

    return exists
