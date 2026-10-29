from pathlib import Path

from django.core.files import File
from django.core.files.storage import default_storage
from django.db import migrations
from PIL import Image

# Infographics from the mentor (2026-10-28), re-encoded to JPEG; the card photo is the tree
# photo cropped out of each infographic's left side.
SEED_DIR = Path(__file__).resolve().parent.parent / "seed" / "gatunki"

# The text version of each infographic, transcribed as printed. Blank cells ("—") on the
# birch infographic are left out. Order follows the mentor's file numbering.
GUIDES = [
    {
        "name": "Dąb szypułkowy",
        "slug": "dab-szypulkowy",
        "latin_name": "Quercus robur",
        "summary": (
            "Dąb szypułkowy to jedno z najbardziej cenionych drzew w Polsce. Jest długowieczny, "
            "ma potężny pokrój i tworzy cenne siedliska dla wielu organizmów. Dzięki rozłożystej "
            "koronie daje cień, poprawia mikroklimat i stanowi ważny element rodzimego krajobrazu."
        ),
        "traits": [
            "Wyjątkowo cenny dla przyrody | Ważne siedlisko dla owadów, ptaków i innych organizmów.",
            "Bardzo duże rozmiary | Dorasta do bardzo dużych rozmiarów.",
            "Długowieczny | Może żyć wiele setek lat.",
            "Wspiera bioróżnorodność | Zapewnia pokarm i schronienie dla licznych gatunków.",
        ],
        "params": [
            "Docelowa wielkość | bardzo duże",
            "Stanowisko | gleby żyzne, umiarkowanie wilgotne",
            "Rodzaj gleby | żyzne, przepuszczalne",
            "Wilgotność | umiarkowanie wilgotne",
            "Nasłonecznienie | dobrze rośnie w miejscach słonecznych",
            "Odporność | dobrze znosi różne warunki",
        ],
        "plant_where": [
            "parki, ogrody, duże tereny zielone",
            "na żyznych i umiarkowanie wilgotnych glebach",
            "w miejscach dobrze nasłonecznionych",
            "z dala od bardzo suchych i jałowych gleb",
        ],
        "dislikes": [
            "bardzo suchych i jałowych gleb",
            "miejsc całkowicie zacienionych",
            "zbyt silnego zagęszczenia i ograniczonej przestrzeni do rozwoju",
            "długotrwałego niedoboru wody",
        ],
    },
    {
        "name": "Dąb bezszypułkowy",
        "slug": "dab-bezszypulkowy",
        "latin_name": "Quercus petraea",
        "summary": (
            "Dąb bezszypułkowy to majestatyczne, długowieczne drzewo liściaste. Tworzy rozłożyste "
            "korony i cenne siedliska dla wielu gatunków owadów, ptaków i innych organizmów. Jest "
            "bardziej odporny na suszę niż dąb szypułkowy i dobrze rośnie na glebach suchszych, "
            "dzięki czemu świetnie sprawdza się w zróżnicowanych warunkach."
        ),
        "traits": [
            "Wysoka wartość przyrodnicza | Cenny dla owadów, ptaków i ssaków.",
            "Lepsza tolerancja suszy | Dobrze rośnie na glebach suchszych i przepuszczalnych.",
            "Długowieczne drzewo | Może żyć wiele setek lat.",
            "Tworzy siedliska | Zapewnia schronienie i pokarm dla wielu gatunków.",
        ],
        "params": [
            "Docelowa wielkość | bardzo duże",
            "Stanowisko | gleby bardziej suche i przepuszczalne",
            "Wymagania glebowe | gleby umiarkowanie suche, dobrze przepuszczalne",
            "Zapotrzebowanie na wodę | umiarkowane",
            "Nasłonecznienie | słoneczne do półcienia",
        ],
        "plant_where": [
            "tereny suche i dobrze nasłonecznione",
            "gleby przepuszczalne, umiarkowanie żyzne",
            "parki, ogrody, tereny zielone i większe działki",
            "w miejscach, gdzie chcemy uzyskać cień i stworzyć cenne siedlisko dla zwierząt",
        ],
        "dislikes": [
            "gleb ciężkich, podmokłych i słabo przepuszczalnych",
            "długotrwałego zalewania",
            "silnego zacienienia",
            "zanieczyszczonych i zdegradowanych gleb",
        ],
    },
    {
        "name": "Lipa drobnolistna",
        "slug": "lipa-drobnolistna",
        "latin_name": "Tilia cordata",
        "summary": (
            "Lipa drobnolistna to jedno z najcenniejszych drzew liściastych w Polsce. Zachwyca "
            "pachnącymi, żółtawymi kwiatami, które pojawiają się latem i przyciągają liczne owady "
            "zapylające. Tworzy rozłożystą koronę, dając przyjemny cień, dlatego jest chętnie "
            "sadzona w parkach, alejach i ogrodach."
        ),
        "traits": [
            "Cenna dla zapylaczy | Przyciąga pszczoły, trzmiele i inne owady.",
            "Pachnące kwiaty | Żółtawe, miododajne kwiaty o silnym, przyjemnym zapachu.",
            "Duża, rozłożysta korona | Daje cień i poprawia jakość powietrza.",
            "Długowieczna | Może rosnąć nawet kilkaset lat.",
        ],
        "params": [
            "Docelowa wielkość | duże",
            "Stanowisko | gleby umiarkowanie żyzne, słońce i półcień",
            "Wymagania glebowe | gleby umiarkowanie żyzne",
            "Zapotrzebowanie na wodę | umiarkowane",
            "Tolerancja na światło | słońce i półcień",
            "Odporność na suszę | umiarkowana",
        ],
        "plant_where": [
            "parki, ogrody, aleje i tereny zielone",
            "przy domach i na większych działkach",
            "miejsca słoneczne lub półcieniste",
            "na glebach umiarkowanie żyznych",
            "z dala od linii energetycznych",
        ],
        "dislikes": [
            "bardzo suchych i jałowych gleb",
            "miejsc całkowicie zacienionych",
            "długotrwałego przesuszenia gleby",
            "zanieczyszczonego powietrza w dużym nasileniu",
            "ograniczonej przestrzeni do rozrostu korony",
        ],
    },
    {
        "name": "Klon zwyczajny",
        "slug": "klon-zwyczajny",
        "latin_name": "Acer platanoides",
        "summary": (
            "Klon zwyczajny to jedno z najczęściej spotykanych drzew liściastych w Polsce. Tworzy "
            "rozłożystą koronę, daje przyjemny cień i dobrze znosi warunki miejskie. Jego "
            "dekoracyjne, dłoniasto klapowane liście przebarwiają się jesienią na złotożółte "
            "odcienie, co czyni go atrakcyjnym drzewem do parków, ogrodów i alei."
        ),
        "traits": [
            "Dekoracyjne liście | Duże, dłoniasto klapowane liście, piękne barwy jesienią.",
            "Daje cień | Tworzy rozłożystą koronę, zapewnia przyjemny cień.",
            "Wczesne źródło pokarmu | Kwiaty dostarczają nektaru dla owadów.",
            "Dobrze się adaptuje | Dobrze znosi warunki miejskie i różne środowiska.",
        ],
        "params": [
            "Docelowa wielkość | duże",
            "Stanowisko | gleby świeże i żyzne",
            "Wymagania glebowe | żyzne, próchniczne i umiarkowanie wilgotne",
            "Zapotrzebowanie na wodę | umiarkowane",
            "Nasłonecznienie | słońce do półcienia",
            "Odporność | dobrze znosi warunki miejskie i różne gleby",
        ],
        "plant_where": [
            "parki, ogrody i duże tereny zielone",
            "aleje, skwery i tereny miejskie",
            "miejsca słoneczne lub półcieniste",
            "na glebach świeżych, żyznych i umiarkowanie wilgotnych",
        ],
        "dislikes": [
            "bardzo suchych i jałowych gleb",
            "długotrwałego przesuszenia",
            "silnego zacienienia",
            "gleb zbitych i podmokłych",
        ],
    },
    {
        "name": "Klon polny",
        "slug": "klon-polny",
        "latin_name": "Acer campestre",
        "summary": (
            "Klon polny to średniej wielkości drzewo liściaste, cenione za naturalny, malowniczy "
            "pokrój i dużą wartość przyrodniczą. Dobrze radzi sobie w cieplejszych warunkach i na "
            "stosunkowo suchych glebach. Jest ważnym źródłem pokarmu dla wielu owadów, ptaków "
            "i drobnych zwierząt, dlatego świetnie sprawdza się w miastach, ogrodach i na terenach "
            "zielonych."
        ),
        "traits": [
            "Średniej wielkości | Osiąga umiarkowane rozmiary, odpowiednie do ogrodów i miast.",
            "Cenny dla przyrody | Ważne źródło pokarmu dla owadów, ptaków i drobnych zwierząt.",
            "Dobrze znosi ciepło i suszę | Dobrze rośnie na stanowiskach ciepłych i stosunkowo suchych.",
            "Dekoracyjna korona | Gęsta, malownicza korona, atrakcyjne liście, piękne jesienne ubarwienie.",
        ],
        "params": [
            "Docelowa wielkość | średnie",
            "Stanowisko | stanowiska ciepłe, także gleby stosunkowo suche",
            "Wymagania glebowe | różne gleby, stosunkowo suche",
            "Zapotrzebowanie na wodę | umiarkowane",
            "Nasłonecznienie | dobrze rośnie na stanowiskach słonecznych",
        ],
        "plant_where": [
            "ogrody, parki, tereny zielone",
            "miejsca ciepłe i słoneczne",
            "na różnych glebach, także stosunkowo suchych",
            "w miastach i na większych działkach",
            "jako drzewo do tworzenia zielonych alei, żywopłotów i zadrzewień",
        ],
        "dislikes": [
            "nadmiernie wilgotnych, podmokłych gleb",
            "długotrwałego zacienienia",
            "bardzo ciężkich, zbitych i stale mokrych gleb",
            "ekstremalnych warunków siedliskowych, które mogą ograniczać jego wzrost",
        ],
    },
    {
        "name": "Grab pospolity",
        "slug": "grab-pospolity",
        "latin_name": "Carpinus betulus",
        "summary": (
            "Grab pospolity to powszechne drzewo liściaste w polskich lasach, parkach "
            "i zadrzewieniach. Ceniony za gęstą koronę i dużą odporność na cięcie. Dobrze znosi "
            "warunki miejskie, tworzy cenny element zieleni, zapewniając schronienie dla ptaków "
            "i innych zwierząt."
        ),
        "traits": [
            "Cenny dla zwierząt | Zapewnia schronienie dla ptaków i innych zwierząt.",
            "Ozdobne liście | Gęsta, zielona korona.",
            "Dobrze znosi miasto | Odporny na trudne warunki miejskie.",
            "Odporny na cięcie | Nadaje się do formowania żywopłotów.",
        ],
        "params": [
            "Docelowa wielkość | średnie/duże",
            "Stanowisko | gleby żyzne i umiarkowanie wilgotne",
            "Wymagania glebowe | żyzne, umiarkowanie wilgotne",
            "Zapotrzebowanie na wodę | umiarkowane",
            "Znaczenie przyrodnicze | schronienie dla ptaków i innych zwierząt",
        ],
        "plant_where": [
            "w lasach, parkach i zadrzewieniach",
            "na terenach zielonych i w ogrodach",
            "w żyznych, umiarkowanie wilgotnych glebach",
            "w miejscach, gdzie potrzebna jest gęsta zieleń i osłona",
        ],
        "dislikes": [
            "bardzo suchych i jałowych gleb",
            "długotrwałego przesuszenia",
            "nadmiernego zalewania i zastojów wody",
            "niekorzystnych, skrajnych warunków siedliskowych",
        ],
    },
    {
        "name": "Brzoza brodawkowata",
        "slug": "brzoza-brodawkowata",
        "latin_name": "Betula pendula",
        "summary": (
            "Brzoza brodawkowata to popularne, szybko rosnące drzewo liściaste. Ma "
            "charakterystyczną, białą korę i delikatne, zwisające gałęzie. Jest gatunkiem "
            "pionierskim, który szybko zasiedla nowe tereny, korzystnie wpływając na środowisko "
            "i stanowiąc siedlisko dla wielu organizmów."
        ),
        "traits": [
            "Cenna dla owadów | Daje pokarm wielu gatunkom owadów i innym organizmom.",
            "Ozdobne liście | Delikatne, jasnozielone, zwisające liście.",
            "Lubi słońce | Najlepiej rośnie na słonecznych stanowiskach.",
            "Gatunek pionierski | Szybko zasiedla nowe tereny, ważny dla wielu organizmów.",
        ],
        "params": [
            "Docelowa wielkość | średnie/duże",
            "Stanowisko | gleby lekkie, piaszczyste, słońce",
        ],
        "plant_where": [
            "na stanowiskach słonecznych",
            "na glebach lekkich i piaszczystych",
            "na terenach otwartych, parkach, ogrodach i większych działkach",
            "w miejscach, gdzie chcemy szybko zazielenić teren",
        ],
        "dislikes": [
            "ciężkich, podmokłych i stale wilgotnych gleb",
            "silnego zacienienia",
            "miejsc o zbyt dużym zanieczyszczeniu gleby i powietrza",
            "długotrwałej suszy",
        ],
    },
    {
        "name": "Olsza czarna",
        "slug": "olsza-czarna",
        "latin_name": "Alnus glutinosa",
        "summary": (
            "Olsza czarna to drzewo typowe dla wilgotnych terenów. Naturalnie rośnie nad rzekami, "
            "jeziorami i na podmokłych obszarach. Dobrze znosi okresowe zalewanie, a dzięki "
            "rozbudowanemu systemowi korzeniowemu stabilizuje gleby i pomaga zatrzymywać wodę "
            "w krajobrazie."
        ),
        "traits": [
            "Lubi wodę | Rośnie na terenach wilgotnych i podmokłych, w pobliżu wód.",
            "Odporna i wytrzymała | Dobrze znosi trudne, wilgotne warunki.",
            "Wspiera retencję | Pomaga zatrzymywać wodę w krajobrazie.",
            "Cenna dla przyrody | Ważna dla siedlisk wilgotnych i wielu gatunków roślin i zwierząt.",
        ],
        "params": [
            "Docelowa wielkość | duże",
            "Stanowisko | tereny wilgotne, podmokłe, okolice wody",
            "Wymagania glebowe | gleby wilgotne, podmokłe",
            "Zapotrzebowanie na wodę | duże",
            "Znaczenie przyrodnicze | ważna dla siedlisk wilgotnych i retencji",
        ],
        "plant_where": [
            "nad rzekami, jeziorami i stawami",
            "na terenach wilgotnych i podmokłych",
            "w miejscach, gdzie chcemy wzmocnić retencję wody",
            "w parkach, terenach zielonych i przy zbiornikach wodnych",
        ],
        "dislikes": [
            "suchych i piaszczystych gleb",
            "długotrwałego przesuszenia",
            "miejsc bardzo zacienionych",
            "gleb ubogich w wodę (bez stałej wilgoci)",
        ],
    },
]


def store(filename):
    """Copy a seed image into the media storage once; return its name and size.

    The check keeps a re-run (or a second database on the same storage, like the test one)
    from piling up renamed copies.
    """
    name = f"gatunki/{filename}"
    path = SEED_DIR / filename
    if not default_storage.exists(name):
        with path.open("rb") as fh:
            name = default_storage.save(name, File(fh, name=filename))
    with Image.open(path) as image:
        return name, image.size


def seed(apps, schema_editor):
    TreeSpecies = apps.get_model("trees", "TreeSpecies")
    SpeciesGuide = apps.get_model("education", "SpeciesGuide")

    for position, data in enumerate(GUIDES, start=1):
        if SpeciesGuide.objects.filter(slug=data["slug"]).exists():
            continue
        # Case-insensitive like the catalogue's unique constraint; Olsza czarna is new to
        # the catalogue and becomes selectable in the registration form.
        species = TreeSpecies.objects.filter(name__iexact=data["name"]).first()
        if species is None:
            species = TreeSpecies.objects.create(name=data["name"])

        infographic, (iw, ih) = store(f"{data['slug']}.jpg")
        photo, (pw, ph) = store(f"{data['slug']}-foto.jpg")
        SpeciesGuide.objects.create(
            species=species,
            slug=data["slug"],
            latin_name=data["latin_name"],
            summary=data["summary"],
            traits="\n".join(data["traits"]),
            params="\n".join(data["params"]),
            plant_where="\n".join(data["plant_where"]),
            dislikes="\n".join(data["dislikes"]),
            infographic=infographic,
            infographic_width=iw,
            infographic_height=ih,
            photo=photo,
            photo_width=pw,
            photo_height=ph,
            position=position * 10,
        )


def unseed(apps, schema_editor):
    """Remove the guides; the files and the catalogue entry stay (trees may use the name)."""
    SpeciesGuide = apps.get_model("education", "SpeciesGuide")
    SpeciesGuide.objects.filter(slug__in=[g["slug"] for g in GUIDES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("education", "0001_species_guides"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
