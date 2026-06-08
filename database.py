import aiosqlite
import json
from datetime import datetime

DB_NAME = "manga_library.db"

async def init_db():
    """Crea las tablas si no existen"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Tabla de mangas (información general)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS mangas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT,
                generos TEXT,
                estado TEXT,
                volumenes TEXT,
                autor TEXT,
                fansub TEXT,
                sinopsis TEXT,
                portada_file_id TEXT,
                fecha_agregado TEXT,
                UNIQUE(nombre)
            )
        ''')
        
        # Tabla de tomos/capítulos (múltiples por manga)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tomos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manga_id INTEGER NOT NULL,
                numero INTEGER NOT NULL,
                pdf_file_id TEXT NOT NULL,
                pdf_file_name TEXT,
                pdf_file_size INTEGER,
                fecha_agregado TEXT,
                FOREIGN KEY (manga_id) REFERENCES mangas(id),
                UNIQUE(manga_id, numero)
            )
        ''')
        
        await db.commit()

async def save_manga(manga_info, portada_file_id):
    """Guarda o actualiza un manga, retorna el ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Verificar si ya existe
        cursor = await db.execute('SELECT id FROM mangas WHERE nombre = ?', (manga_info['nombre'],))
        existing = await cursor.fetchone()
        
        if existing:
            # Actualizar portada si es nuevo
            await db.execute(
                'UPDATE mangas SET portada_file_id = ? WHERE id = ?',
                (portada_file_id, existing[0])
            )
            await db.commit()
            return existing[0]
        
        # Insertar nuevo manga
        cursor = await db.execute('''
            INSERT INTO mangas 
            (nombre, tipo, generos, estado, volumenes, autor, fansub, sinopsis,
             portada_file_id, fecha_agregado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            manga_info['nombre'],
            manga_info.get('tipo', 'Manga'),
            json.dumps(manga_info.get('generos', [])),
            manga_info.get('estado', 'Desconocido'),
            manga_info.get('volumenes', '?'),
            manga_info.get('autor', 'Desconocido'),
            manga_info.get('fansub', 'Desconocido'),
            manga_info.get('sinopsis', 'Sin sinopsis'),
            portada_file_id,
            datetime.now().isoformat()
        ))
        await db.commit()
        return cursor.lastrowid

async def save_tomo(manga_id, numero, pdf_info):
    """Guarda un tomo/capítulo de un manga"""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute('''
                INSERT INTO tomos 
                (manga_id, numero, pdf_file_id, pdf_file_name, pdf_file_size, fecha_agregado)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                manga_id,
                numero,
                pdf_info['file_id'],
                pdf_info['file_name'],
                pdf_info['file_size'],
                datetime.now().isoformat()
            ))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_manga_with_tomos(manga_id):
    """Obtiene un manga con todos sus tomos"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # Info del manga
        async with db.execute('SELECT * FROM mangas WHERE id = ?', (manga_id,)) as cursor:
            manga = await cursor.fetchone()
            if not manga:
                return None
        
        # Tomos del manga
        async with db.execute(
            'SELECT * FROM tomos WHERE manga_id = ? ORDER BY numero',
            (manga_id,)
        ) as cursor:
            tomos = await cursor.fetchall()
        
        result = dict(manga)
        result['generos'] = json.loads(result['generos']) if result['generos'] else []
        result['tomos'] = [dict(t) for t in tomos]
        return result

async def get_all_mangas():
    """Obtiene todos los mangas con conteo de tomos"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT m.*, COUNT(t.id) as total_tomos 
            FROM mangas m 
            LEFT JOIN tomos t ON m.id = t.manga_id 
            GROUP BY m.id 
            ORDER BY m.fecha_agregado DESC
        ''') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def search_mangas(query):
    """Busca mangas por nombre o autor"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        search = f"%{query}%"
        async with db.execute('''
            SELECT m.*, COUNT(t.id) as total_tomos 
            FROM mangas m 
            LEFT JOIN tomos t ON m.id = t.manga_id 
            WHERE m.nombre LIKE ? OR m.autor LIKE ? 
            GROUP BY m.id 
            ORDER BY m.nombre
        ''', (search, search)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]