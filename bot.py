import logging
import os
import re
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import database as db

# ========================
# CARGAR VARIABLES DE ENTORNO
# ========================
load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    raise ValueError("❌ No se encontró TELEGRAM_BOT_TOKEN en el archivo .env")

# Almacenamiento temporal en memoria
user_sessions = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========================
# COMANDOS
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🈴 ¡Bienvenido a tu Biblioteca de Manga!\n\n"
        "Para agregar un manga:\n"
        "1. Reenvíame el mensaje con la *portada e información*\n"
        "2. Reenvíame los *PDFs* de los tomos (todos los que quieras)\n"
        "3. Cuando quieras agregar otro manga, reenvía una *nueva portada*\n\n"
        "Comandos:\n"
        "/biblioteca - Ver todos tus mangas\n"
        "/buscar [nombre] - Buscar un manga",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Cómo usar:*\n\n"
        "Reenvía los mensajes de tu canal de manga:\n\n"
        "1️⃣ *Primero:* Mensaje con portada + descripción\n"
        "2️⃣ *Luego:* Todos los PDFs que quieras del mismo manga\n"
        "3️⃣ *Para cambiar de manga:* Envía una nueva portada\n\n"
        "El bot seguirá aceptando PDFs hasta que envíes una nueva portada.\n\n"
        "Comandos:\n"
        "/biblioteca - Ver tu colección\n"
        "/buscar [texto] - Buscar por nombre o autor",
        parse_mode='Markdown'
    )

async def biblioteca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra todos los mangas guardados"""
    mangas = await db.get_all_mangas()
    
    if not mangas:
        await update.message.reply_text("📚 Tu biblioteca está vacía. Usa /start para agregar mangas.")
        return
    
    mensaje = f"📚 *Tu Biblioteca ({len(mangas)} mangas):*\n\n"
    
    for manga in mangas[:10]:
        generos = json.loads(manga['generos']) if manga['generos'] else []
        generos_str = ', '.join(generos[:3]) if generos else 'N/A'
        tomos = manga.get('total_tomos', 0)
        
        mensaje += (
            f"📕 *{manga['nombre']}*\n"
            f"   ✍️ {manga['autor']} | 📊 {manga['estado']}\n"
            f"   📚 {manga['volumenes']} | 📦 {tomos} tomo(s)\n"
            f"   🏷️ {generos_str}\n\n"
        )
    
    if len(mangas) > 10:
        mensaje += f"_...y {len(mangas) - 10} más_"
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca mangas por nombre o autor"""
    query = ' '.join(context.args)
    
    if not query:
        await update.message.reply_text("🔍 Usa: /buscar [nombre o autor]")
        return
    
    mangas = await db.search_mangas(query)
    
    if not mangas:
        await update.message.reply_text(f"❌ No encontré mangas con '{query}'")
        return
    
    mensaje = f"🔍 *Resultados para '{query}':*\n\n"
    
    for manga in mangas:
        generos = json.loads(manga['generos']) if manga['generos'] else []
        tomos = manga.get('total_tomos', 0)
        mensaje += (
            f"📕 *{manga['nombre']}*\n"
            f"   ✍️ {manga['autor']} | 📊 {manga['estado']}\n"
            f"   📦 {tomos} tomo(s)\n"
            f"   🏷️ {', '.join(generos[:5]) if generos else 'N/A'}\n\n"
        )
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

# ========================
# PARSER DE METADATA
# ========================
def parse_manga_info(text):
    """Extrae la información del manga del texto"""
    if not text:
        return None
    
    info = {}
    
    match = re.search(r'[🈴📕]▹?Nombre:\s*(.+?)(?=\n|$)', text)
    info['nombre'] = match.group(1).strip() if match else "Desconocido"
    
    match = re.search(r'✔️▹?Tipo:\s*(.+?)(?=\n|$)', text)
    info['tipo'] = match.group(1).strip() if match else "Manga"
    
    match = re.search(r'✔️▹?Géneros:\s*(.+?)(?=✔️▹?Estado|🔰▹?Sinopsis|$)', text, re.DOTALL)
    if match:
        generos_raw = match.group(1)
        generos = re.split(r'[•,\n]+', generos_raw)
        info['generos'] = [g.strip() for g in generos if g.strip() and len(g.strip()) > 2]
    else:
        info['generos'] = []
    
    match = re.search(r'✔️▹?Estado:\s*(.+?)(?=\n|$)', text)
    info['estado'] = match.group(1).strip() if match else "Desconocido"
    
    match = re.search(r'✔️▹?Vol[úu]menes?:\s*(.+?)(?=\n|$)', text)
    if not match:
        match = re.search(r'✔️▹?Cap[íi]tulos?:\s*(.+?)(?=\n|$)', text)
    info['volumenes'] = match.group(1).strip() if match else "?"
    
    match = re.search(r'✔️▹?Autor:\s*(.+?)(?=\n|$)', text)
    info['autor'] = match.group(1).strip() if match else "Desconocido"
    
    match = re.search(r'✔️▹?Fansub:\s*(.+?)(?=\n|$)', text)
    info['fansub'] = match.group(1).strip() if match else "Desconocido"
    
    match = re.search(r'🔰▹?Sinopsis:\s*(.+)', text, re.DOTALL)
    info['sinopsis'] = match.group(1).strip() if match else "Sin sinopsis"
    
    return info

# ========================
# PROCESAR MENSAJES
# ========================
async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    text = message.text or message.caption or ""
    document = message.document
    photos = message.photo
    
    print(f"\n{'='*50}")
    print(f"📩 Mensaje de usuario {user_id}")
    print(f"   Texto: {text[:100] if text else 'Sin texto'}...")
    print(f"   Documento: {document.file_name if document else 'No'}")
    print(f"   Fotos: {len(photos) if photos else 0}")
    
    session = user_sessions.get(user_id)
    session_active = session and (datetime.now() - session['timestamp']) < timedelta(minutes=30)
    
    # CASO 1: Portada + Metadata (siempre inicia nueva sesión)
    if photos and text:
        print("   → Detectado: NUEVA PORTADA + METADATA")
        
        manga_info = parse_manga_info(text)
        
        if manga_info and manga_info['nombre'] != "Desconocido":
            # Si había sesión anterior, notificar que se cerró
            if session_active:
                tomos_anteriores = session.get('tomos_count', 0)
                await message.reply_text(
                    f"📕 *Cambiando de manga...*\n"
                    f"Se guardaron {tomos_anteriores} tomo(s) del manga anterior.\n\n"
                    f"Ahora agregando: *{manga_info['nombre']}*",
                    parse_mode='Markdown'
                )
            
            # Guardar/actualizar manga en BD y obtener ID
            manga_id = await db.save_manga(manga_info, photos[-1].file_id)
            
            # Nueva sesión
            user_sessions[user_id] = {
                'manga_id': manga_id,
                'manga_info': manga_info,
                'portada_file_id': photos[-1].file_id,
                'timestamp': datetime.now(),
                'tomos_count': 0,
                'last_tomo_number': 0
            }
            
            resumen = (
                f"✅ *Manga listo para recibir tomos:*\n\n"
                f"📕 {manga_info['nombre']}\n"
                f"✍️ Autor: {manga_info['autor']}\n"
                f"📊 Estado: {manga_info['estado']}\n"
                f"📚 Volúmenes: {manga_info['volumenes']}\n"
                f"🏷️ Géneros: {', '.join(manga_info['generos']) if manga_info['generos'] else 'N/A'}\n\n"
                f"🖼️ Portada guardada\n\n"
                f"📥 *Envíame todos los PDFs que quieras agregar.*\n"
                f"Cuando termines, envía una *nueva portada* para cambiar de manga."
            )
            await message.reply_text(resumen, parse_mode='Markdown')
        else:
            await message.reply_text("⚠️ No pude detectar la información del manga. Verifica el formato.")
    
    # CASO 2: PDF con sesión activa
    elif document and session_active:
        print(f"   → Detectado: PDF (sesión activa: {session['manga_info']['nombre']})")
        
        if document.mime_type != 'application/pdf':
            await message.reply_text("⚠️ El archivo no es un PDF. Envíame un archivo .pdf")
            return
        
        # Incrementar número de tomo
        session['last_tomo_number'] += 1
        tomo_num = session['last_tomo_number']
        
        # Guardar tomo en BD
        guardado = await db.save_tomo(
            manga_id=session['manga_id'],
            numero=tomo_num,
            pdf_info={
                'file_id': document.file_id,
                'file_name': document.file_name,
                'file_size': document.file_size
            }
        )
        
        session['tomos_count'] = tomo_num
        session['timestamp'] = datetime.now()  # Renovar sesión
        
        if guardado:
            resumen = (
                f"✅ *Tomo guardado:*\n\n"
                f"📕 {session['manga_info']['nombre']}\n"
                f"📄 Tomo #{tomo_num}: {document.file_name}\n"
                f"💾 Tamaño: {document.file_size / 1024 / 1024:.2f} MB\n\n"
                f"📦 Total de tomos en este manga: {tomo_num}\n\n"
                f"📥 *Sigue enviando más PDFs* o envía una *nueva portada* para cambiar de manga."
            )
        else:
            resumen = (
                f"⚠️ *Este tomo ya estaba guardado.*\n"
                f"📄 {document.file_name}\n\n"
                f"📦 Total de tomos: {tomo_num - 1}"
            )
        
        await message.reply_text(resumen, parse_mode='Markdown')
    
    # CASO 3: PDF sin sesión
    elif document and not session_active:
        print("   → Detectado: PDF SIN SESIÓN")
        await message.reply_text(
            "📄 Recibí un PDF, pero no tengo información del manga.\n\n"
            "Por favor, envíame primero el mensaje con:\n"
            "• La portada\n• La descripción del manga\n\n"
            "Y luego reenvíame los PDFs."
        )
    
    # CASO 4: Otro
    else:
        print("   → Detectado: MENSAJE NO RECONOCIDO")
        await message.reply_text(
            "🤔 No entendí qué quieres hacer.\n\n"
            "Para agregar un manga:\n"
            "1️⃣ Reenvía el mensaje con portada + info\n"
            "2️⃣ Reenvía todos los PDFs que quieras\n"
            "3️⃣ Para cambiar de manga, envía una nueva portada\n\n"
            "Usa /help para más información."
        )

# ========================
# MAIN
# ========================
async def post_init(application):
    """Inicializa la base de datos al arrancar"""
    await db.init_db()
    print("✅ Base de datos inicializada")

def main():
    print("🤖 Iniciando MangaBot...")
    print("="*50)
    
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("biblioteca", biblioteca))
    application.add_handler(CommandHandler("buscar", buscar))
    application.add_handler(MessageHandler(filters.ALL, process_message))
    
    print("✅ Bot listo. Esperando mensajes...")
    print("="*50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()