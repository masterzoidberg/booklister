"""SQLModel database models and FTS utilities."""

import sys
import os

# Import from parent directory's models.py
# We need to add the parent directory to sys.path temporarily
_parent_dir = os.path.dirname(os.path.dirname(__file__))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Import the models module from parent directory
import importlib.util
_models_path = os.path.join(_parent_dir, "models.py")
_spec = importlib.util.spec_from_file_location("_models_parent", _models_path)
_models_parent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_models_parent)

# Re-export everything
Book = _models_parent.Book
Image = _models_parent.Image
Export = _models_parent.Export
Setting = _models_parent.Setting
Token = _models_parent.Token
FTSBook = _models_parent.FTSBook
BookStatus = _models_parent.BookStatus
ConditionGrade = _models_parent.ConditionGrade
create_fts_table = _models_parent.create_fts_table
create_fts_triggers = _models_parent.create_fts_triggers

__all__ = [
    "Book",
    "Image",
    "Export",
    "Setting",
    "Token",
    "FTSBook",
    "BookStatus",
    "ConditionGrade",
    "create_fts_table",
    "create_fts_triggers",
]
