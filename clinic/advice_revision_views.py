"""Read-only, physician-only editorial history; never a patient handout."""
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .access import manager_required
from .models import Advice, AdviceRevision


@never_cache
@manager_required
@require_GET
def history(request, pk):
    advice = get_object_or_404(Advice, pk=pk)
    page = Paginator(advice.revisions.select_related('actor'), 20).get_page(request.GET.get('page'))
    return render(request, 'clinic/advice_editorial_history.html', {'section':'advice', 'advice':advice, 'page':page})


@never_cache
@manager_required
@require_GET
def revision_detail(request, pk, revision_pk):
    revision = get_object_or_404(AdviceRevision.objects.select_related('advice', 'actor'), pk=revision_pk, advice_id=pk)
    return render(request, 'clinic/advice_revision_detail.html', {'section':'advice', 'advice':revision.advice,
        'revision':revision})
