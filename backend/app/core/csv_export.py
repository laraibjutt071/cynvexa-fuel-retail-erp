import csv
import io

from fastapi.responses import StreamingResponse


def csv_response(filename: str, fieldnames: list[str], rows: list[dict]) -> StreamingResponse:
    """
    The one place every dashboard report's CSV export builds its response -
    so every export shares the same quoting/line-ending behavior rather
    than each endpoint rolling its own. `rows` must already contain
    display-ready values (str/number); this does no formatting of its
    own.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
