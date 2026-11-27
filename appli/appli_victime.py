"""appli_victime — visionneuse légère des photos du dossier image_victime.

Pour chaque image : miniature cliquable, données EXIF (date/heure, géolocalisation
GPS) affichées en dessous, et un champ « Nombre de victimes » laissé vide
(à compléter plus tard, hors EXIF).

Lancement :
    python appli_victime.py                 # dossier image_victime (à côté du script)
    python appli_victime.py CHEMIN_DOSSIER  # un autre dossier d'images

Dépendance : Pillow (pip install Pillow). Tkinter est inclus avec Python :
aucune compilation nécessaire.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

try:
    from PIL import ExifTags, Image, ImageOps, ImageTk
except ImportError:
    raise SystemExit("Pillow est requis pour lire les images et l'EXIF : pip install Pillow")

DOSSIER_PAR_DEFAUT = Path(__file__).resolve().parent / "image_victime"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

MINIATURE = (280, 190)   # taille max de la miniature (largeur, hauteur)
LARGEUR_CARTE = 320      # largeur d'une carte -> sert au calcul du nombre de colonnes
ESPACEMENT = 14

# Palette
FOND = "#eef1f5"
CARTE = "#ffffff"
BORDURE = "#d4d9e0"
TEXTE = "#1f2937"
SECONDAIRE = "#6b7280"
ACCENT = "#2563eb"
ACCENT_FONCE = "#1d4ed8"
POLICE = "Segoe UI"


# --------------------------------------------------------------------------- EXIF

def _dms_vers_degres(valeur, ref: str) -> float:
    """Convertit (degrés, minutes, secondes) EXIF en degrés décimaux signés."""
    degres = float(valeur[0]) + float(valeur[1]) / 60 + float(valeur[2]) / 3600
    if str(ref).upper() in ("S", "W"):
        degres = -degres
    return degres


def formater_date(brute) -> str | None:
    """'2025:11:20 14:32:10' -> '20/11/2025 à 14:32:10' (brut si format inconnu)."""
    if not brute:
        return None
    texte = str(brute)
    try:
        return datetime.strptime(texte, "%Y:%m:%d %H:%M:%S").strftime("%d/%m/%Y à %H:%M:%S")
    except ValueError:
        return texte


def formater_gps(gps: tuple[float, float]) -> str:
    lat, lon = gps
    return (f"{abs(lat):.6f}° {'N' if lat >= 0 else 'S'}, "
            f"{abs(lon):.6f}° {'E' if lon >= 0 else 'O'}")


def lire_exif(chemin: Path) -> dict:
    """Date/heure et GPS d'une image ; None si absents ou image illisible."""
    resultat = {"date": None, "date_brute": None, "gps": None}
    try:
        with Image.open(chemin) as img:
            exif = img.getexif()
            sous_ifd = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        return resultat
    # DateTimeOriginal (36867), sinon DateTimeDigitized (36868), sinon DateTime (306)
    brute = sous_ifd.get(36867) or sous_ifd.get(36868) or exif.get(306)
    resultat["date_brute"] = str(brute) if brute else None
    resultat["date"] = formater_date(brute)
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    lat, lat_ref = gps_ifd.get(2), gps_ifd.get(1)
    lon, lon_ref = gps_ifd.get(4), gps_ifd.get(3)
    if lat and lon and lat_ref and lon_ref:
        resultat["gps"] = (_dms_vers_degres(lat, lat_ref), _dms_vers_degres(lon, lon_ref))
    return resultat


def lister_images(dossier: Path) -> list[tuple[Path, dict]]:
    """Images du dossier triées par date EXIF (les sans-date d'abord, puis par nom)."""
    images = []
    for chemin in sorted(dossier.iterdir()):
        if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS:
            images.append((chemin, lire_exif(chemin)))
    images.sort(key=lambda t: (t[1]["date_brute"] or "", t[0].name))
    return images


# ------------------------------------------------------------------------Divers

def ouvrir_avec_systeme(chemin: Path) -> None:
    if sys.platform == "win32":
        os.startfile(chemin)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(chemin)])
    else:
        subprocess.run(["xdg-open", str(chemin)])


# --------------------------------------------------------------------------- GUI

class AppliVictime(tk.Tk):
    def __init__(self, dossier: Path):
        super().__init__()
        self.iconbitmap('appli\img\drone_icon.ico')
        self.dossier = Path(dossier)
        self.cartes: list[tk.Widget] = []
        self.geometry("1120x720")
        self.minsize(760, 500)
        self.configure(bg=FOND)
        self._configurer_styles()
        self._construire_interface()
        self.charger()

    def _configurer_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")  # look un peu plus moderne que le thème par défaut
        except tk.TclError:
            pass
        style.configure("TFrame", background=FOND)
        style.configure("TLabel", background=FOND, foreground=TEXTE, font=(POLICE, 10))
        style.configure("Titre.TLabel", font=(POLICE, 18, "bold"), foreground=ACCENT)
        style.configure("SousTitre.TLabel", foreground=SECONDAIRE, font=(POLICE, 10))
        style.configure("TButton", font=(POLICE, 10), padding=(12, 6))
        style.configure("Accent.TButton", font=(POLICE, 10, "bold"),
                        foreground="white", background=ACCENT, padding=(14, 6))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_FONCE), ("pressed", ACCENT_FONCE)])

    def _construire_interface(self) -> None:
        entete = ttk.Frame(self)
        entete.pack(fill="x", padx=18, pady=(14, 8))
        entete.columnconfigure(0, weight=1)
        ttk.Label(entete, text="VicRec — Reconnaissance de personnes en détresse", style="Titre.TLabel").grid(row=0, column=0, sticky="w")
        # self.lbl_dossier = ttk.Label(entete, text=str(self.dossier), style="SousTitre.TLabel")
        # self.lbl_dossier.grid(row=1, column=0, sticky="w", pady=(2, 0))
        boutons = ttk.Frame(entete)
        boutons.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(boutons, text="Choisir un dossier…",
                   command=self.choisir_dossier).pack(side="left", padx=4)
        ttk.Button(boutons, text="Rafraîchir", style="Accent.TButton",
                   command=self.charger).pack(side="left", padx=4)
        ttk.Button(boutons, text="Ouvrir le dossier",
                   command=lambda: ouvrir_avec_systeme(self.dossier)).pack(side="left", padx=4)

        corps = ttk.Frame(self)
        corps.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        self.canvas = tk.Canvas(corps, bg=FOND, highlightthickness=0)
        barre = ttk.Scrollbar(corps, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barre.set)
        barre.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interieur = ttk.Frame(self.canvas)
        self._fenetre = self.canvas.create_window((0, 0), window=self.interieur, anchor="nw")
        self.interieur.bind("<Configure>",
                            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._molette)   # Windows / macOS
        self.canvas.bind("<Button-4>", self._molette)     # Linux : haut
        self.canvas.bind("<Button-5>", self._molette)     # Linux : bas

        self.lbl_statut = ttk.Label(self, text="", style="SousTitre.TLabel", anchor="w")
        self.lbl_statut.pack(fill="x", padx=18, pady=(0, 10))

    # ------------------------------------------------------------------ contenu

    def charger(self) -> None:
        for carte in self.cartes:
            carte.destroy()
        self.cartes = []
        self.title(f"VicRec")
        # self.lbl_dossier.config(text=str(self.dossier))
        self.canvas.yview_moveto(0)
        if not self.dossier.is_dir():
            self.lbl_statut.config(text=f"Dossier introuvable : {self.dossier}")
            return
        images = lister_images(self.dossier)
        if not images:
            ttk.Label(self.interieur, style="SousTitre.TLabel", justify="center",
                      text="Aucune image dans ce dossier.\n"
                           "Ajoute des photos dans image_victime puis clique sur « Rafraîchir »."
                      ).grid(padx=40, pady=60)
            self.lbl_statut.config(text="0 image")
            return
        for chemin, exif in images:
            self.cartes.append(self._creer_carte(chemin, exif))
        self._reorganiser()
        self.lbl_statut.config(text=f"{len(images)} image(s) — {self.dossier}")

    def _creer_carte(self, chemin: Path, exif: dict) -> tk.Frame:
        carte = tk.Frame(self.interieur, bg=BORDURE, highlightthickness=0)  # bordure 1 px
        contenu = tk.Frame(carte, bg=CARTE, highlightthickness=0)
        contenu.pack(padx=1, pady=1, fill="both", expand=True)

        # Miniature (clic = ouvrir l'image en grand dans la visionneuse du système)
        photo = None
        try:
            with Image.open(chemin) as img:
                img = ImageOps.exif_transpose(img)  # respecte l'orientation EXIF
                img.thumbnail(MINIATURE, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
        except Exception:
            photo = None
        lbl_photo = tk.Label(contenu, bg=CARTE)
        if photo is not None:
            lbl_photo.config(image=photo, cursor="hand2")
            lbl_photo.image = photo  # conserve la référence (sinon l'image disparaît)
            lbl_photo.bind("<Button-1>", lambda e, p=chemin: ouvrir_avec_systeme(p))
        else:
            lbl_photo.config(text="(aperçu indisponible)", fg=SECONDAIRE, width=36, height=10)
        lbl_photo.pack(padx=10, pady=(10, 6))

        tk.Label(contenu, text=chemin.name, bg=CARTE, fg=TEXTE,
                 font=(POLICE, 10, "bold")).pack(padx=10, anchor="w")
        tk.Label(contenu, text=f"Date : {exif['date'] or 'non renseignée'}",
                 bg=CARTE, fg=SECONDAIRE, font=(POLICE, 9)).pack(padx=10, anchor="w", pady=(2, 0))

        if exif["gps"]:
            lat, lon = exif["gps"]
            ligne_gps = tk.Frame(contenu, bg=CARTE)
            ligne_gps.pack(padx=10, anchor="w", pady=(2, 0))
            tk.Label(ligne_gps, text=f"GPS : {formater_gps(exif['gps'])}",
                     bg=CARTE, fg=SECONDAIRE, font=(POLICE, 9)).pack(side="left")
            tk.Button(ligne_gps, text="voir sur la carte", bg=CARTE, fg=ACCENT, bd=0,
                      cursor="hand2", font=(POLICE, 9, "underline"),
                      command=lambda la=lat, lo=lon:
                      webbrowser.open(f"https://www.google.com/maps?q={la},{lo}")
                      ).pack(side="left", padx=(6, 0))
        else:
            tk.Label(contenu, text="GPS : non renseigné", bg=CARTE, fg=SECONDAIRE,
                     font=(POLICE, 9)).pack(padx=10, anchor="w", pady=(2, 0))

        # Description « nombre de victimes » — laissée vide, hors EXIF (à adapter plus tard)
        tk.Frame(contenu, bg=BORDURE, height=1).pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(contenu, text="Nombre de victimes :", bg=CARTE, fg=TEXTE,
                 font=(POLICE, 9, "bold")).pack(padx=10, anchor="w")
        entree = tk.Entry(contenu, width=8, font=(POLICE, 10), relief="solid", bd=1,
                          highlightthickness=1, highlightcolor=BORDURE)
        entree.pack(padx=10, anchor="w", pady=(2, 12), ipady=2)
        return carte

    # ------------------------------------------------------------------ eventos

    def choisir_dossier(self) -> None:
        choix = filedialog.askdirectory(initialdir=str(self.dossier), title="Dossier d'images")
        if choix:
            self.dossier = Path(choix)
            self.charger()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._fenetre, width=event.width)
        self._reorganiser()

    def _reorganiser(self) -> None:
        largeur = self.canvas.winfo_width()
        if largeur < 50:
            return
        colonnes = max(1, largeur // (LARGEUR_CARTE + ESPACEMENT))
        for i, carte in enumerate(self.cartes):
            carte.grid(row=i // colonnes, column=i % colonnes,
                       padx=ESPACEMENT // 2, pady=ESPACEMENT // 2, sticky="n")

    def _molette(self, event) -> None:
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")


def main() -> None:
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else DOSSIER_PAR_DEFAUT
    AppliVictime(dossier).mainloop()


if __name__ == "__main__":
    main()
