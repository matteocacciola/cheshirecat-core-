import os
import shutil
import uuid
from typing import Final

from cat.adapters.factory_adapter import UpdaterFactory
from cat.factory.custom_plugin_uploader import BaseUploader


class PluginTransferAdapter:
    def __init__(self, uploader_from: BaseUploader, uploader_to: BaseUploader, updater_factory: UpdaterFactory):
        self.uploader_from: Final[BaseUploader] = uploader_from
        self.uploader_to: Final[BaseUploader] = uploader_to
        self.updater_factory: Final[UpdaterFactory] = updater_factory

    def transfer(self):
        # create tmp directory
        tmp_folder_name = f"/tmp/{uuid.uuid1()}"
        os.mkdir(tmp_folder_name)

        # try to download the files from the old uploader
        self.uploader_from.download_directory(
            self.updater_factory.old_setting["value"]["destination_path"], tmp_folder_name
        )

        # now, try to upload the files to the new storage
        self.uploader_to.upload_directory(
            tmp_folder_name, self.updater_factory.new_setting["value"]["destination_path"]
        )

        # cleanup
        if os.path.exists(tmp_folder_name):
            shutil.rmtree(tmp_folder_name)