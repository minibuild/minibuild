from __future__ import print_function
import sys
import threading
if sys.version_info.major < 3:
    import Queue as queue
else:
    import queue

from .error_utils import *
from .toolset_base import ToolsetActionOutput

class ActionEntry:
    def __init__(self, action, ctx):
        self.action = action
        self.ctx = ctx

class ActionResponse:
    def __init__(self, worker_number, messages):
        self.worker_number = worker_number
        self.messages = messages


class ToolsetActionOutputInMemory(ToolsetActionOutput):
    def __init__(self):
        self.messages = []

    def report_message(self, msg):
        self.messages.append(msg)

class ActionsPoolSharedContext:
    def __init__(self, jobs_count, input_queue, output_queue):
        self.jobs_count = jobs_count
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.error_occured = threading.Event()
        self.error_reasons = []
        self.error_reason_guard = threading.RLock()
        self.rebuilt = False

    def reset(self):
        self.error_reasons = []
        self.rebuilt = False
        self.error_occured.clear()


def worker_perform(worker_number, item, ctl):
    if ctl.error_occured.is_set():
        return
    locked = False
    try:
        output = ToolsetActionOutputInMemory()
        ret = item.action.safe_execute(item.ctx, output)
        if ret.exit_code is not None:
            ctl.error_reason_guard.acquire()
            locked = True
            ctl.error_reasons += [(ret, ActionResponse(worker_number, messages=output.messages))]
            ctl.error_occured.set()
        else:
            if ret.rebuilt:
                ctl.error_reason_guard.acquire()
                locked = True
                ctl.rebuilt = True
                ctl.error_reason_guard.release()
                locked = False
            if output.messages:
                rsp = ActionResponse(worker_number, messages=output.messages)
                ctl.output_queue.put(rsp)
    finally:
        if locked:
            ctl.error_reason_guard.release()


def print_action_output(verbose, verbose_fmt, jobs_count, item):
    for msg in item.messages:
        if verbose and jobs_count > 1:
            msg = verbose_fmt.format(item.worker_number, msg)
        print(msg)


def print_main(verbose, verbose_fmt, ctl):
    while True:
        item = ctl.output_queue.get()
        if item is None:
            ctl.output_queue.task_done()
            break
        try:
            print_action_output(verbose, verbose_fmt, ctl.jobs_count, item)
        finally:
            ctl.output_queue.task_done()


def worker_main(worker_number, ctl):
    while True:
        item = ctl.input_queue.get()
        if item is None:
            ctl.input_queue.task_done()
            break
        try:
            worker_perform(worker_number, item, ctl)
        except Exception as err:
            ctl.error_occured.set()
            etype, value, tb = sys.exc_info()
            error_text = traceback_to_string(etype, value, tb)
            rsp = ActionResponse(worker_number, messages=[error_text])
            ctl.output_queue.put(rsp)
        finally:
            ctl.input_queue.task_done()


class ActionsPool:
    def __init__(self, jobs_count, verbose):
        self.jobs_count = jobs_count
        self.verbose = verbose
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.ctl = ActionsPoolSharedContext(self.jobs_count, self.input_queue, self.output_queue)
        self.workers = []
        self.printer = None
        if jobs_count < 10:
            self.verbose_fmt = '[{}] {}'
        else:
            self.verbose_fmt = '[{:2}] {}'

    def put(self, action, ctx):
        item = ActionEntry(action, ctx)
        self.input_queue.put(item)

    def join(self):
        try:
            self.input_queue.join()
        except KeyboardInterrupt:
            self.ctl.error_occured.set()
            self.input_queue.join()
            self.output_queue.join()
            raise BuildSystemException("Keyboard interrupt")
        self.output_queue.join()
        if self.ctl.error_occured.is_set():
            if not self.ctl.error_reasons:
                raise BuildSystemException("Internal bug in actions pool.")
            for errret, errmsg in self.ctl.error_reasons:
                print_action_output(self.verbose, self.verbose_fmt, self.jobs_count, errmsg)
                err_details = errret.error_text
                if self.verbose and self.jobs_count > 1:
                    err_details = self.verbose_fmt.format(errmsg.worker_number, err_details)
                print(err_details)
            raise BuildSystemSysExit(self.ctl.error_reasons[0][0].exit_code)
        rebuilt = self.ctl.rebuilt
        self.ctl.reset()
        return rebuilt

    def init(self):
        printer = threading.Thread(target=print_main, name='buildsys-print', args=(self.verbose, self.verbose_fmt, self.ctl))
        printer.start()
        self.printer = printer
        for idx in range(self.jobs_count):
            th = threading.Thread(target=worker_main, name='buildsys-worker-{}'.format(idx + 1), args=(idx + 1, self.ctl))
            th.start()
            self.workers.append(th)

    def shutdown(self):
        active_workers_count = len(self.workers)
        for idx in range(self.jobs_count):
            self.input_queue.put(None)
        for idx in range(active_workers_count):
            self.workers[idx].join()
        if self.printer is not None:
            self.output_queue.put(None)
            self.printer.join()
