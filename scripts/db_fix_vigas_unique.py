import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mes_vigas_web.settings")

import django

django.setup()

from django.db import connections


def main() -> None:
    conn = connections["mes"]
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE public.vigas DROP CONSTRAINT IF EXISTS uq_viga")
        cur.execute(
            """
            UPDATE public.vigas
            SET codigo_viga = regexp_replace(codigo_viga, '-[0-9][0-9]$', '')
            WHERE total_piezas > 1
              AND codigo_viga ~ '-[0-9][0-9]$'
              AND CAST(right(codigo_viga, 2) AS int) = pieza_no
            """
        )
        normalized = cur.rowcount
        cur.execute(
            """
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'public.vigas'::regclass
              AND contype = 'u'
            ORDER BY conname
            """
        )
        uniques = cur.fetchall()
    conn.commit()
    print("dropped uq_viga (if existed)")
    print("normalized_rows", normalized)
    print("remaining_unique_constraints", uniques)


if __name__ == "__main__":
    main()
