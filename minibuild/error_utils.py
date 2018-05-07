import inspect
import os.path


class BuildSystemException(Exception):
    def __init__(self, text, exit_code=None, frame=1):
        if exit_code is None:
            frame_info = inspect.stack()[frame]
            msg = '[{}({})] {}'.format(os.path.basename(frame_info[1]), frame_info[2], text)
        else:
            msg = text
        Exception.__init__(self, msg)
        self.exit_code = 126
        if exit_code is not None:
            self.exit_code = exit_code

    def to_exit_code(self):
        return self.exit_code

class BuildSystemPureVirtualCall(BuildSystemException):
    def __init__(self, class_instance):
        frame_info = inspect.stack()[1]
        BuildSystemException.__init__(self, "Pure virtual call - {}::{}".format(type(class_instance).__name__, frame_info[3]), frame=3)