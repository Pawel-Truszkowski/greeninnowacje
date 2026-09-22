from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm, UserChangeForm

from .models import User


class AdminUserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ["email", "display_name", "role"]


class AdminUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class RegistrationForm(forms.ModelForm):
    """Self-service volunteer sign-up — deliberately just 3 fields (UI doc §8.6)."""

    password = forms.CharField(
        label="Hasło",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Min. 10 znaków.",
    )

    class Meta:
        model = User
        fields = ["display_name", "email"]  # + the declared `password` field
        labels = {"display_name": "Jak mamy się do Ciebie zwracać?", "email": "E-mail"}
        widgets = {
            "display_name": forms.TextInput(attrs={"autocomplete": "nickname"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def _post_clean(self):
        super()._post_clean()
        # Validate after the instance is populated so similarity checks see email/name.
        password = self.cleaned_data.get("password")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.VOLUNTEER
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Nieprawidłowy e-mail lub hasło.",
        "inactive": "To konto jest nieaktywne.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"
        self.fields["username"].widget = forms.EmailInput(
            attrs={"autocomplete": "email", "autofocus": True}
        )
