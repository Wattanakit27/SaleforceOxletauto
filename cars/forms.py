from django import forms

from . import constants as C
from .models import Car, branch_pairs


class CarForm(forms.ModelForm):
    class Meta:
        model = Car
        fields = [
            "branch", "plate", "brand", "model", "year", "color", "km",
            "status", "priority", "book_status", "tax_due_date", "doc_registration",
            "photo", "note",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2}),
            "tax_due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # สาขาจาก DB (fallback constant)
        self.fields["branch"] = forms.ChoiceField(
            choices=branch_pairs(), label="สาขา")
        # ใส่คลาส bootstrap-ish ให้ทุก field
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            if isinstance(f.widget, (forms.CheckboxInput,)):
                continue
            f.widget.attrs["class"] = (css + " inp").strip()
