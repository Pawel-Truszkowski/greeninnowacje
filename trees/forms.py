from django import forms
from django.utils import timezone

from .geo import is_in_poland
from .models import Tree
from .selectors import active_species_names

# Sentinel choice that reveals the free-text field (PoC: "Inny (wpiszę ręcznie)").
OTHER_SPECIES = "__other__"


class TreeRegistrationForm(forms.ModelForm):
    """Registering a tree in the field (UI doc §8.5): as few required fields as possible.

    Coordinates come from the device GPS (or a dragged map pin) through hidden inputs,
    so they are validated here rather than trusted. The species comes from the catalogue
    (`TreeSpecies`); anything else must go through the "Inny" option, and such a name is
    stored on the tree without joining the catalogue — that stays the admin's decision.
    """

    species = forms.ChoiceField(label="Gatunek drzewa", choices=[])
    species_other = forms.CharField(
        label="Inny gatunek",
        required=False,
        max_length=120,
        help_text="Wypełnij, jeśli wybrano „Inny”.",
    )
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built per instance, so a species added in the admin shows up without a restart.
        self.fields["species"].choices = (
            [("", "— wybierz gatunek —")]
            + [(name, name) for name in active_species_names()]
            + [(OTHER_SPECIES, "Inny (wpiszę ręcznie)")]
        )

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

        if cleaned.get("species") == OTHER_SPECIES:
            # From here on `species` is a plain name again, so register_tree() and
            # Tree.species need to know nothing about the sentinel.
            other = (cleaned.get("species_other") or "").strip()
            if other:
                cleaned["species"] = other
            else:
                self.add_error("species_other", "Wpisz nazwę gatunku albo wybierz go z listy.")
        return cleaned

    def registration_fields(self):
        """Model fields for `register_tree` (everything except the locality name)."""
        return {name: self.cleaned_data[name] for name in self.Meta.fields}
