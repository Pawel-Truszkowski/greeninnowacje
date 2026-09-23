from django import forms
from django.utils import timezone

from .geo import is_in_poland
from .models import Tree


class TreeRegistrationForm(forms.ModelForm):
    """Registering a tree in the field (UI doc §8.5): as few required fields as possible.

    Coordinates come from the device GPS (or a dragged map pin) through hidden inputs,
    so they are validated here rather than trusted.
    """

    locality_name = forms.CharField(
        label="Miejscowość",
        required=False,
        help_text="Zostaw puste — ustalimy ją z lokalizacji.",
    )

    class Meta:
        model = Tree
        fields = ["species", "planted_on", "planted_by", "notes", "lat", "lng", "gps_accuracy_m"]
        labels = {
            "species": "Gatunek drzewa",
            "planted_on": "Data posadzenia",
            "planted_by": "Kto sadził (osoba lub organizacja)",
            "notes": "Notatki",
        }
        widgets = {
            "planted_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "lat": forms.HiddenInput(),
            "lng": forms.HiddenInput(),
            "gps_accuracy_m": forms.HiddenInput(),
        }

    def clean_planted_on(self):
        planted_on = self.cleaned_data["planted_on"]
        if planted_on > timezone.localdate():
            raise forms.ValidationError("Data posadzenia nie może być z przyszłości.")
        return planted_on

    def clean(self):
        cleaned = super().clean()
        lat, lng = cleaned.get("lat"), cleaned.get("lng")
        if lat is None or lng is None:
            raise forms.ValidationError(
                "Brak lokalizacji drzewa. Włącz GPS albo wskaż miejsce na mapie."
            )
        if not is_in_poland(lat, lng):
            raise forms.ValidationError("Współrzędne wyglądają na spoza Polski — sprawdź pinezkę.")
        return cleaned

    def registration_fields(self):
        """Model fields for `register_tree` (everything except the locality name)."""
        return {name: self.cleaned_data[name] for name in self.Meta.fields}
