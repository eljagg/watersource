"""Public repository views: open-data catalogue, dataset pages, CSV/GeoJSON downloads, published documents."""
from __future__ import annotations

import csv
import itertools

from django.db.models import F
from django.http import FileResponse, Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from .datasets import DATASETS
from .models import DocumentCategory, PublishedDocument

PREVIEW_ROWS = 15


def _documents():
    return PublishedDocument.objects.filter(is_published=True).select_related("unit")


@require_GET
def index(request):
    """Catalogue: datasets, published documents, developer links, terms."""
    docs = _documents()
    by_cat = [(label, [d for d in docs if d.category == code]) for code, label in DocumentCategory.choices]
    return render(request, "opendata/index.html", {"datasets": list(DATASETS.values()), "documents_by_category": [(label, ds) for label, ds in by_cat if ds],
                                                   "document_count": docs.count()})


@require_GET
def dataset(request, slug):
    """One dataset: description, fields, preview, downloads."""
    ds = DATASETS.get(slug)
    if ds is None:
        raise Http404
    rows = list(itertools.islice(ds.rows(), PREVIEW_ROWS))
    return render(request, "opendata/dataset.html", {"ds": ds, "rows": rows, "count": ds.count(), "updated": ds.updated(),
                                                     "related": [d for d in DATASETS.values() if d is not ds]})


class _Echo:
    """File-like object whose write() returns the value, for streaming CSV."""

    def write(self, value):
        """Return the row as written."""
        return value


@require_GET
def dataset_csv(request, slug):
    """Streamed CSV download (UTF-8 with BOM so Excel opens it correctly); streamed, so not cached."""
    ds = DATASETS.get(slug)
    if ds is None:
        raise Http404
    names = [f.name for f in ds.fields]
    writer = csv.DictWriter(_Echo(), fieldnames=names, extrasaction="ignore")

    def gen():
        yield "﻿"
        yield writer.writeheader()
        for r in ds.rows():
            yield writer.writerow({k: ("" if v is None else v) for k, v in r.items()})

    resp = StreamingHttpResponse(gen(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="wra-{slug}.csv"'
    return resp


@require_GET
@cache_page(600)
def dataset_geojson(request, slug):
    """GeoJSON for spatial datasets."""
    ds = DATASETS.get(slug)
    if ds is None or not ds.spatial:
        raise Http404
    resp = JsonResponse(ds.geojson())
    resp["Content-Type"] = "application/geo+json"
    resp["Content-Disposition"] = f'attachment; filename="wra-{slug}.geojson"'
    return resp


@require_GET
def document(request, pk, name=None):
    """Download a published document (counts downloads; nothing unpublished is served)."""
    doc = get_object_or_404(_documents(), pk=pk)
    PublishedDocument.objects.filter(pk=doc.pk).update(downloads=F("downloads") + 1)
    filename = doc.original_name or f"{slugify(doc.title)}.{doc.extension.lower()}"
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=filename)
