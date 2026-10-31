"""Forms behind the admin panel (spec §4).

The thresholds form is the interesting one: these four numbers decide when a volunteer
is told a tree is dying, so the validation lives here and is shared by the page and the
API — a bad combination (SOON >= URGENT) would silently make "water soon" unreachable.
"""

from django import forms
from django.db.models import Max

from accounts.models import CoordinatorArea, User
from core.models import DEFAULTS, Config
from education.models import SpeciesGuide
from education.services import CARD_PHOTO_SIZE
from trees.forms import OTHER_SPECIES, PHOTO_INPUT_ATTRS
from trees.images import InvalidImage, process_upload
from trees.models import Locality, Tree, TreeSpecies
from trees.selectors import active_species_names

THRESHOLD_LABELS = {
    "RAIN_WINDOW_DAYS": "Okno pogodowe (dni)",
    "RAIN_THRESHOLD_MM": "Próg opadu w oknie (mm)",
    "DAYS_SOON": "Dni bez wody → „wkrótce podlać”",
    "DAYS_URGENT": "Dni bez wody → „pilnie podlać”",
}


class ThresholdsForm(forms.Form):
    """Drought thresholds from the `config` table (spec §3, §6.2)."""

    RAIN_WINDOW_DAYS = forms.IntegerField(min_value=1, max_value=30)
    RAIN_THRESHOLD_MM = forms.DecimalField(min_value=0, max_digits=5, decimal_places=1)
    DAYS_SOON = forms.IntegerField(min_value=1, max_value=60)
    DAYS_URGENT = forms.IntegerField(min_value=1, max_value=90)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, field in self.fields.items():
            field.label = THRESHOLD_LABELS[key]

    @classmethod
    def initial_from_config(cls):
        stored = dict(Config.objects.values_list("key", "value"))
        return {key: stored.get(key, default) for key, default in DEFAULTS.items()}

    def clean(self):
        cleaned = super().clean()
        soon, urgent = cleaned.get("DAYS_SOON"), cleaned.get("DAYS_URGENT")
        if soon and urgent and soon >= urgent:
            self.add_error(
                "DAYS_URGENT",
                "Próg „pilnie” musi być większy niż „wkrótce” — inaczej status „wkrótce” "
                "nigdy nie wystąpi.",
            )
        return cleaned

    def save(self):
        for key, value in self.cleaned_data.items():
            Config.objects.update_or_create(key=key, defaults={"value": str(value)})
        return self.cleaned_data


class UserAdminForm(forms.ModelForm):
    """Role, account status and — for a coordinator — the area they oversee.

    The area belongs on this screen rather than its own: a coordinator without localities
    oversees nothing, so granting the role separately would create one that silently does
    not work.
    """

    localities = forms.ModelMultipleChoiceField(
        label="Obszar koordynatora",
        queryset=Locality.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Miejscowości pod nadzorem. Przy innych rolach pomijane.",
    )

    class Meta:
        model = User
        fields = ["role", "is_active"]
        labels = {"role": "Rola", "is_active": "Konto aktywne"}

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        if self.instance.pk:
            self.fields["localities"].initial = Locality.objects.filter(
                coordinators__user=self.instance
            )

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            self._sync_areas(user)
        return user

    def _sync_areas(self, user):
        """Make the stored areas match the form — including emptying them on a demotion.

        A volunteer left with `CoordinatorArea` rows would be a coordinator in all but name
        the moment somebody restored the role.
        """
        wanted = set()
        if user.role == User.Role.COORDINATOR:
            wanted = {locality.pk for locality in self.cleaned_data.get("localities", [])}

        areas = CoordinatorArea.objects.filter(user=user)
        areas.exclude(locality_id__in=wanted).delete()
        existing = set(areas.values_list("locality_id", flat=True))
        CoordinatorArea.objects.bulk_create(
            [CoordinatorArea(user=user, locality_id=pk) for pk in wanted - existing]
        )

    def clean(self):
        cleaned = super().clean()
        if self.editor and self.editor.pk == self.instance.pk:
            # Locking yourself out takes one click and a database session to undo.
            if cleaned.get("role") != User.Role.ADMIN or not cleaned.get("is_active"):
                raise forms.ValidationError(
                    "Nie możesz odebrać uprawnień ani dezaktywować własnego konta."
                )
        return cleaned


class TreeAdminForm(forms.ModelForm):
    """Editing a tree (spec §4). Species comes from the catalogue, as in registration."""

    species = forms.ChoiceField(label="Gatunek drzewa", choices=[])
    species_other = forms.CharField(
        label="Inny gatunek", required=False, max_length=120, help_text="Jeśli wybrano „Inny”."
    )

    class Meta:
        model = Tree
        fields = ["species", "planted_on", "planted_by", "notes", "locality", "lifecycle"]
        labels = {
            "planted_on": "Data posadzenia",
            "planted_by": "Kto sadził",
            "notes": "Notatki",
            "locality": "Miejscowość",
            "lifecycle": "Cykl życia",
        }
        widgets = {
            "planted_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        catalogue = active_species_names()
        current = self.instance.species if self.instance and self.instance.pk else None
        # A tree may carry a species that was later retired — keep it selectable so
        # editing notes does not force renaming the tree.
        extra = [current] if current and current not in catalogue else []
        self.fields["species"].choices = [(name, name) for name in catalogue + extra] + [
            (OTHER_SPECIES, "Inny (wpiszę ręcznie)")
        ]
        self.fields["locality"].queryset = Locality.objects.all()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("species") == OTHER_SPECIES:
            other = (cleaned.get("species_other") or "").strip()
            if other:
                cleaned["species"] = other
            else:
                self.add_error("species_other", "Wpisz nazwę gatunku albo wybierz go z listy.")
        return cleaned


class SpeciesGuideForm(forms.ModelForm):
    """A knowledge base page about one species, images included.

    The species is picked from the registration catalogue, like a tree's, or typed in — the
    service then adds it to the catalogue. Images are plain `FileField`s for the reason given
    in `trees.forms.PhotoForm`; `clean_<field>` runs them through `process_upload`, so a bad
    file is an error under its own field and `cleaned_data` carries the re-encoded image.
    """

    species = forms.ChoiceField(label="Gatunek", choices=[])
    species_other = forms.CharField(
        label="Inny gatunek",
        required=False,
        max_length=120,
        help_text="Jeśli wybrano „Inny”. Gatunek trafi też na listę przy rejestracji drzewa.",
    )
    infographic = forms.FileField(
        label="Infografika",
        required=False,
        widget=forms.ClearableFileInput(attrs=PHOTO_INPUT_ATTRS),
    )
    photo = forms.FileField(
        label="Zdjęcie na kartę",
        required=False,
        widget=forms.ClearableFileInput(attrs=PHOTO_INPUT_ATTRS),
        help_text="Zostanie przycięte do pionowego kadru 4:5 — najlepiej całe drzewo na środku.",
    )

    class Meta:
        model = SpeciesGuide
        fields = [
            "latin_name",
            "summary",
            "traits",
            "params",
            "plant_where",
            "dislikes",
            "position",
            "is_published",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
            "traits": forms.Textarea(attrs={"rows": 6}),
            "params": forms.Textarea(attrs={"rows": 7}),
            "plant_where": forms.Textarea(attrs={"rows": 4}),
            "dislikes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        adding = not self.instance.pk
        # A species has one guide: offer those still without one, and this guide's own.
        free = TreeSpecies.objects.filter(is_active=True, guide__isnull=True)
        names = list(free.values_list("name", flat=True))
        if not adding:
            names = sorted([self.instance.species.name, *names])
            self.initial["species"] = self.instance.species.name
            keep = "Zostaw puste, aby zachować obecny plik."
            self.fields["infographic"].help_text = keep
            self.fields["photo"].help_text = f"{keep} {self.fields['photo'].help_text}"
        else:
            last = SpeciesGuide.objects.aggregate(last=Max("position"))["last"]
            # Steps of ten, like the seed: room to slot a species in between later.
            self.initial["position"] = (last or 0) + 10
        self.fields["species"].choices = [(name, name) for name in names] + [
            (OTHER_SPECIES, "Inny (wpiszę ręcznie)")
        ]
        self.fields["infographic"].required = adding
        self.fields["photo"].required = adding

    def _processed(self, field, **options):
        upload = self.cleaned_data.get(field)
        if not upload:
            return None
        try:
            return process_upload(upload, **options)
        except InvalidImage as problem:
            raise forms.ValidationError(str(problem)) from None

    def clean_infographic(self):
        return self._processed("infographic")

    def clean_photo(self):
        return self._processed("photo", fit=CARD_PHOTO_SIZE)

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("species")
        typed = name == OTHER_SPECIES
        if typed:
            name = " ".join((cleaned.get("species_other") or "").split())
            if not name:
                self.add_error("species_other", "Wpisz nazwę gatunku albo wybierz go z listy.")
                return cleaned
            cleaned["species"] = name

        taken = SpeciesGuide.objects.filter(species__name__iexact=name)
        if name and taken.exclude(pk=self.instance.pk).exists():
            self.add_error(
                "species_other" if typed else "species",
                f"Gatunek „{name}” ma już opis. Znajdziesz go na liście gatunków.",
            )
        return cleaned
