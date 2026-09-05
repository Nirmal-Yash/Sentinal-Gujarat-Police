"""Preloaded AI model registry shared across forked Linux workers."""
from __future__ import annotations

YOLO_MODEL = None
OCR_READER = None

def set_yolo_model(model):
    global YOLO_MODEL
    YOLO_MODEL = model

def get_yolo_model():
    return YOLO_MODEL

def set_ocr_reader(reader):
    global OCR_READER
    OCR_READER = reader

def get_ocr_reader():
    return OCR_READER
