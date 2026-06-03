from flask import request

from api_m.domains.base_api import BaseAPI
from api_m.services import (
    NativeDialogError,
    NativeDialogUnavailableError,
    NativeDirectoryPickerService,
)


class NativeDialogsAPI(BaseAPI):
    def __init__(self, app, user_manager=None, db=None, model_manager=None, services=None):
        super().__init__(app, user_manager, db, model_manager, services=services)
        if self.services:
            self.native_directory_picker = self.services.native_directory_picker
        else:
            self.native_directory_picker = NativeDirectoryPickerService()

    def register(self):
        self.app.add_url_rule(
            "/api/native/directory-picker",
            view_func=self.handle_directory_picker_post,
            methods=["POST"],
        )

    def handle_directory_picker_post(self):
        auth = self.authenticate_request(request)
        if auth is not True:
            return auth

        data = self.get_request_json(request)
        try:
            directory = self.native_directory_picker.select_directory(
                initial_path=data.get("initial_path"),
                title=data.get("title"),
            )
        except (NativeDialogUnavailableError, NativeDialogError) as error:
            return self.error_from_exception(error)

        return self.ok({
            "canceled": directory is None,
            "directory": directory,
        })
