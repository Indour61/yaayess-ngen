import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template

from xhtml2pdf import pisa

from ..models import Invoice


# ==========================================================
# DASHBOARD FACTURES
# ==========================================================

@login_required
def invoices_dashboard(request):
    factures = (
        Invoice.objects
        .select_related("group")
        .order_by("-mois")
    )

    return render(
        request,
        "accounts/invoices.html",
        {
            "factures": factures,
        },
    )


# ==========================================================
# FACTURE PDF
# ==========================================================

@login_required
def invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(
        Invoice,
        id=invoice_id,
    )

    template = get_template(
        "accounts/invoice_pdf.html"
    )

    logo_path = os.path.join(
        settings.BASE_DIR,
        "static",
        "images",
        "logo.png",
    )

    html = template.render(
        {
            "invoice": invoice,
            "logo_path": logo_path,
        }
    )

    response = HttpResponse(
        content_type="application/pdf"
    )

    # Téléchargement ou aperçu navigateur
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = (
            f'attachment; filename="facture_{invoice.id}.pdf"'
        )
    else:
        response["Content-Disposition"] = (
            f'inline; filename="facture_{invoice.id}.pdf"'
        )

    pisa_status = pisa.CreatePDF(
        html,
        dest=response,
    )

    if pisa_status.err:
        return HttpResponse(
            "Erreur lors de la génération du PDF.",
            status=500,
        )

    return response