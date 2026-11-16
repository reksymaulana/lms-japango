from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bunpou

STARTER_GRAMMAR = [
    {
        "level": "N5",
        "title": "NはNです",
        "explanation": "Pola dasar untuk menyatakan topik dan identitas: は menandai topik, sedangkan です berarti “adalah”.",
        "examples": [{"japanese": "わたしは学生です。", "translation": "Saya adalah pelajar."}],
    },
    {
        "level": "N5",
        "title": "NはNじゃありません",
        "explanation": "Bentuk negatif sopan dari です untuk mengatakan bahwa sesuatu bukan atau tidak termasuk suatu kategori.",
        "examples": [{"japanese": "これは本じゃありません。", "translation": "Ini bukan buku."}],
    },
    {
        "level": "N5",
        "title": "NもNです",
        "explanation": "Partikel も menggantikan は atau が dengan arti “juga”.",
        "examples": [{"japanese": "田中さんも先生です。", "translation": "Tanaka juga seorang guru."}],
    },
    {
        "level": "N5",
        "title": "NをVます",
        "explanation": "Partikel を menandai objek langsung dari kata kerja.",
        "examples": [{"japanese": "毎朝パンを食べます。", "translation": "Saya makan roti setiap pagi."}],
    },
    {
        "level": "N5",
        "title": "Waktu に Vます",
        "explanation": "Partikel に digunakan setelah waktu yang spesifik untuk menunjukkan kapan suatu kegiatan terjadi.",
        "examples": [{"japanese": "毎朝七時に起きます。", "translation": "Saya bangun pukul tujuh setiap pagi."}],
    },
    {
        "level": "N5",
        "title": "Tempat へ／に行きます",
        "explanation": "Partikel へ atau に menandai tujuan pada kata kerja perpindahan seperti 行きます (pergi).",
        "examples": [{"japanese": "学校へ行きます。", "translation": "Saya pergi ke sekolah."}],
    },
    {
        "level": "N4",
        "title": "Vたことがある",
        "explanation": "Bentuk lampau biasa + ことがある menyatakan pengalaman yang pernah dialami.",
        "examples": [{"japanese": "日本へ行ったことがあります。", "translation": "Saya pernah pergi ke Jepang."}],
    },
    {
        "level": "N4",
        "title": "Vたり、Vたりする",
        "explanation": "Menyebutkan beberapa contoh kegiatan, biasanya dengan bentuk lampau biasa + り, lalu diakhiri する.",
        "examples": [{"japanese": "週末は本を読んだり、映画を見たりします。", "translation": "Akhir pekan saya melakukan hal seperti membaca buku dan menonton film."}],
    },
    {
        "level": "N4",
        "title": "Vます-stem ながら",
        "explanation": "Menghubungkan dua kegiatan yang dilakukan bersamaan. Kegiatan sebelum ながら biasanya menjadi kegiatan pendamping.",
        "examples": [{"japanese": "音楽を聞きながら勉強します。", "translation": "Saya belajar sambil mendengarkan musik."}],
    },
    {
        "level": "N4",
        "title": "Vてしまう",
        "explanation": "Menyatakan suatu tindakan selesai sepenuhnya; dalam konteks tertentu juga menunjukkan penyesalan atau kejadian yang tidak diinginkan.",
        "examples": [{"japanese": "財布を忘れてしまいました。", "translation": "Saya tidak sengaja lupa membawa dompet."}],
    },
    {
        "level": "N4",
        "title": "Vたほうがいい",
        "explanation": "Bentuk lampau biasa + ほうがいい digunakan untuk memberi saran bahwa sesuatu sebaiknya dilakukan.",
        "examples": [{"japanese": "早く寝たほうがいいです。", "translation": "Sebaiknya tidur lebih awal."}],
    },
    {
        "level": "N4",
        "title": "普通形 + と思います",
        "explanation": "Bentuk biasa + と思います digunakan untuk menyampaikan pendapat atau perkiraan pribadi.",
        "examples": [{"japanese": "明日は雨が降ると思います。", "translation": "Saya rasa besok akan turun hujan."}],
    },
    {
        "level": "N3",
        "title": "V辞書形／ない形 + ようにする",
        "explanation": "Menyatakan usaha atau kebiasaan yang sengaja dilakukan agar suatu hal terjadi atau tidak terjadi.",
        "examples": [{"japanese": "毎日漢字を復習するようにしています。", "translation": "Saya berusaha membiasakan diri mengulang Kanji setiap hari."}],
    },
    {
        "level": "N3",
        "title": "V辞書形 + ことにする",
        "explanation": "Menyatakan keputusan yang dibuat oleh pembicara sendiri.",
        "examples": [{"japanese": "来月から毎朝走ることにしました。", "translation": "Saya memutuskan untuk mulai berlari setiap pagi bulan depan."}],
    },
    {
        "level": "N3",
        "title": "V辞書形／Nの + ために",
        "explanation": "Menunjukkan tujuan atau manfaat yang ingin dicapai.",
        "examples": [{"japanese": "日本で働くために、日本語を勉強しています。", "translation": "Saya belajar bahasa Jepang agar bisa bekerja di Jepang."}],
    },
    {
        "level": "N3",
        "title": "Nばかり",
        "explanation": "Menunjukkan bahwa sesuatu dilakukan berulang kali atau terlalu sering; sering membawa nuansa bahwa pilihan lain kurang dilakukan.",
        "examples": [{"japanese": "弟はゲームばかりしています。", "translation": "Adik laki-laki saya main gim terus."}],
    },
    {
        "level": "N3",
        "title": "普通形 + わけではない",
        "explanation": "Menyatakan bahwa sesuatu tidak sepenuhnya benar atau tidak berlaku dalam semua keadaan.",
        "examples": [{"japanese": "甘いものが嫌いなわけではありません。", "translation": "Bukan berarti saya tidak suka makanan manis."}],
    },
    {
        "level": "N3",
        "title": "Vたところ",
        "explanation": "Menyatakan bahwa suatu tindakan baru saja selesai atau pembicara baru saja berada pada tahap tersebut.",
        "examples": [{"japanese": "今、駅に着いたところです。", "translation": "Saya baru saja sampai di stasiun."}],
    },
]


async def seed_grammar(session: AsyncSession) -> None:
    existing_titles = set(await session.scalars(select(Bunpou.title)))
    new_entries = [
        Bunpou(**entry)
        for entry in STARTER_GRAMMAR
        if entry["title"] not in existing_titles
    ]
    if new_entries:
        session.add_all(new_entries)
        await session.commit()
