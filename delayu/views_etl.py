"""#32 — детали запуска ETL с протоколом ошибок."""
import json

from django.shortcuts import get_object_or_404, render
from django.views import View

from delayu.mixins import ModulePermissionMixin
from delayu.models import EtlRun
from delayu.views_platform import _ctx_membership


class EtlRunModalView(ModulePermissionMixin, View):
    module_code = "M70"

    def get(self, request, pk):
        m = _ctx_membership(self)
        run = get_object_or_404(EtlRun, pk=pk, job__subsystem=m.subsystem)
        return render(
            request,
            "platform/infra/_etl_run_modal.html",
            {
                "run": run,
                "errors_json": json.dumps(run.error_rows or [], ensure_ascii=False, indent=2),
            },
        )
