import cv2
import numpy as np

from yolo_pi.detector import Detector, Timings
from yolo_pi.processing import Detection

import filter

def intersection_over_unit(detections: list[Detection], seuil=0.65) -> list[Detection]:
    """Calcule une matrice carrée de taille detections.len() dont les coefficients sont les scores iou
    Filtre les détections en fonction du score iou : s'il dépasse un certain seuil pour deux images,
    on n'en garde qu'une parmi les deux"""
    boxes = np.array([
        [det.x1, det.y1, det.x2, det.y2]
        for det in detections
    ], dtype=float)

    if boxes.size != 0:
        areas = (boxes[:, 2] - boxes[:, 0])*(boxes[:, 3] - boxes[:, 1])

        x1 = np.maximum(boxes[:, None, 0], boxes[None, :, 0])
        y1 = np.maximum(boxes[:, None, 1], boxes[None, :, 1])
        x2 = np.minimum(boxes[:, None, 2], boxes[None, :, 2])
        y2 = np.minimum(boxes[:, None, 3], boxes[None, :, 3])

        intersection = np.maximum(0, x2 - x1)*np.maximum(0, y2 - y1)
        union = areas[:, None] + areas[None, :] - intersection
        iou_mat = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        
        new_detections = detections.copy()

        for i in range(len(detections)):
            for j in range(i+1, len(detections)):
                if iou_mat[i, j] >= seuil:
                    if (detections[i] in new_detections) and (detections[j] in new_detections):
                        if detections[j].score > detections[i].score:
                            new_detections.remove(detections[i])
                        else:
                            new_detections.remove(detections[j])
        return new_detections
    return []


def build_rotations(shape: tuple, n_rotations: int) -> list:
    """Précalcule, pour chaque angle 360/n * i, la matrice M de cv2.warpAffine, la
    taille du canvas élargi (équivalent du reshape=True de scipy, image jamais rognée)
    et Minv = invertAffineTransform(M).

    Par défaut warpAffine(src, M, size) traite M comme la transformation DIRECTE
    origine -> tournée (il l'inverse en interne pour échantillonner) : pour projeter
    une boîte détectée dans l'image TOURNÉE vers l'image d'origine, on applique Minv.
    """
    h, w = shape[:2]
    mats = []
    step = 360.0 / n_rotations
    for i in range(n_rotations):
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), step * i, 1.0)
        cos, sin = abs(M[0, 0]), abs(M[0, 1])
        nw = int(round(h * sin + w * cos))
        nh = int(round(h * cos + w * sin))
        # Recentre le contenu dans le canvas élargi.
        M[0, 2] += (nw - w) / 2.0
        M[1, 2] += (nh - h) / 2.0
        mats.append((M, (nw, nh), cv2.invertAffineTransform(M)))
    return mats

def merge_detections(detections_per_angle: list, mats: list, shape: tuple) -> list[Detection]:
    """Fusion : garde l'angle qui a détecté le plus de personnes, puis projette ses
    boîtes dans le repère de l'image d'origine en appliquant Minv (inverse de la
    matrice de rotation : l'image tournée -> l'image d'origine).

    Les coins sont remis dans l'ordre (min/max) et recadrés sur l'image : les boîtes
    ne peuvent plus sortir du cadre ni avoir x1 > x2.
    """
    h, w = shape[:2]
    out = []
    for idx in range(len(detections_per_angle)):
        for d in detections_per_angle[idx]:
            _, _, Minv = mats[idx]
            pts = np.array([[d.x1, d.y1, 1.0],
                [d.x2, d.y1, 1.0],
                [d.x2, d.y2, 1.0],
                [d.x1, d.y2, 1.0]])
            corners = (Minv @ pts.T).T[:, :2]
            xs, ys = corners[:, 0], corners[:, 1]
            x1n, y1n, x2n, y2n = xs.min(), ys.min(), xs.max(), ys.max()
            out.append(Detection(
                float(np.clip(x1n, 0, w)), float(np.clip(y1n, 0, h)),
                float(np.clip(x2n, 0, w)), float(np.clip(y2n, 0, h)),
                d.score, d.class_id,
            ))
    return out


def detect_rotations(pool, detector: Detector, frame0: np.ndarray, mats: list, workers: int):
    """Lance une inférence par rotation (en parallèle si un pool est fourni) et renvoie
    (liste des détections filtrées par angle, Timings CUMULÉS sur toutes les rotations)."""
    def one(i):
        M, size, _ = mats[i]
        rotated = cv2.warpAffine(frame0, M, size, flags=cv2.INTER_LINEAR,
                                 borderValue=(114, 114, 114))
        dets, t = detector(rotated)
        return filter.filter(dets), t  # personnes uniquement

    if pool is not None and workers > 1:
        results = list(pool.map(one, range(len(mats))))
    else:
        results = [one(i) for i in range(len(mats))]

    all_dets = [r[0] for r in results]
    t_total = Timings(
        sum(r[1].pre_ms for r in results),
        sum(r[1].infer_ms for r in results),
        sum(r[1].post_ms for r in results),
    )
    return all_dets, t_total