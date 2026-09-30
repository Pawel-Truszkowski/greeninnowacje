from django import forms
from django.utils import timezone

from .geo import is_in_poland
from .models import Tree
from .selectors import active_species_names

# Sentinel choice that reveals the free-text field (PoC: "Inny (wpiszę ręcznie)").
OTHER_SPECIES = "__other__"

# `capture` makes a phone open the rear camera instead of the file browser (UI doc §106).
PHOTO_INPUT_ATTRS = {"accept": "image/*", "capture": "environment"}


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
    # Hidden behind the „zmień" toggle under the map (PoC): the locality normally comes from
    # the coordinates, and typing it is the exception, not the rule.
    locality_name = forms.CharField(
        label="Miejscowość",
        required=False,
        help_text="Wpisz tylko wtedy, gdy automatyczne rozpoznanie się pomyli.",
    )
    photo = forms.FileField(
        label="Zdjęcie drzewa",
        required=False,
        help_text="Możesz dodać je od razu — albo później z karty drzewa.",
        widget=forms.ClearableFileInput(attrs=PHOTO_INPUT_ATTRS),
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


class PhotoForm(forms.Form):
    """One photo, taken on the spot (UI doc §106: „aparat/galeria").

    A plain `FileField`, not an `ImageField`: `trees.images.process_upload` is the only place
    that judges a file, so the page and the JSON API refuse identical uploads for identical
    reasons.
    """

    image = forms.FileField(
        label="Zdjęcie drzewa",
        widget=forms.ClearableFileInput(attrs=PHOTO_INPUT_ATTRS),
    )
