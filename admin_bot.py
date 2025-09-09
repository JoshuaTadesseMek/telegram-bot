import os
import logging
import pandas as pd
import json
from google.oauth2.service_account import Credentials
import gspread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes, CallbackQueryHandler
)
from dotenv import load_dotenv
from datetime import datetime
import io
import tempfile
import contextlib

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
AUTHENTICATE, ADMIN_MENU, EDIT_QUESTIONS, NEW_QUESTION = range(4)

# File paths
EXCEL_FILE = 'data.xlsx'
QUESTIONS_FILE = 'questions.json'
ADMIN_USERS_FILE = 'admin_users.json'

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1HfK7_BYyewklYn32m82qteGgByzTTxA6_fovaDYdl74"
QUESTIONS_SHEET_NAME = "Questions"  # Name of the worksheet where questions will be stored

# Path to the mounted secret file
CREDS_FILE = "/etc/secrets/reflected-cycle-448109-p5-65cedb726569.json"

credentials = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
client = gspread.authorize(credentials)
sheet = client.open_by_key(SHEET_ID).sheet1


@contextlib.contextmanager
def get_excel_file():
    """Context manager that yields a temporary Excel file and cleans it up afterwards."""
    file_path = None
    try:
        file_path = sheet_to_excel_local()
        if file_path and os.path.exists(file_path):
            yield file_path
        else:
            yield None
    finally:
        # Clean up: this runs AFTER the 'with' block is done
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.warning(f"Could not delete temp Excel file: {e}")

def get_client():
    """Authorize and return Google Sheets client"""
    try:
        logger.info(f"Attempting to authorize with credentials file: {CREDS_FILE}")
        if not os.path.exists(CREDS_FILE):
            logger.error(f"Credentials file not found at: {CREDS_FILE}")
            return None
            
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        logger.info("Google Sheets client authorized successfully")
        return client
    except Exception as e:
        logger.error(f"Error authorizing Google Sheets client: {e}")
        return None

def sheet_to_excel_local():
    """Fetch Google Sheet and save as a local Excel file. Returns file path or None."""
    try:
        logger.info("Starting sheet_to_excel_local process")
        
        client = get_client()
        if not client:
            logger.error("Failed to get Google Sheets client")
            return None

        logger.info(f"Attempting to open sheet with ID: {SHEET_ID}")
        sheet = client.open_by_key(SHEET_ID).sheet1
        logger.info("Sheet opened successfully")
        
        logger.info("Fetching all records from sheet")
        data = sheet.get_all_records()
        logger.info(f"Retrieved {len(data)} records from Google Sheets")
        
        df = pd.DataFrame(data)
        logger.info(f"Created DataFrame with shape: {df.shape}")

        if df.empty:
            logger.warning("DataFrame is empty - no data to export")
            return None

        # Use a temporary file
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "telegram_bot_data.xlsx")
        logger.info(f"Creating Excel file at: {file_path}")
        
        df.to_excel(file_path, index=False)
        
        # Verify file was created
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"Excel file created successfully: {file_path}, size: {file_size} bytes")
            
            # Additional debug: check file content
            try:
                test_df = pd.read_excel(file_path)
                logger.info(f"Test read successful. File contains {len(test_df)} rows, {len(test_df.columns)} columns")
            except Exception as test_error:
                logger.warning(f"Test read failed but file exists: {test_error}")
                
            return file_path
        else:
            logger.error("Excel file was not created successfully")
            return None

    except Exception as e:
        logger.error(f"Error generating local Excel file: {e}", exc_info=True)
        return None

def get_dataframe():
    """Fetch fresh dataframe directly from Google Sheets (no Excel needed)"""
    try:
        logger.info("Fetching DataFrame directly from Google Sheets")
        client = get_client()
        if not client:
            return pd.DataFrame()
            
        sheet = client.open_by_key(SHEET_ID).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        logger.info(f"Direct DataFrame fetch successful. Shape: {df.shape}")
        return df
    except Exception as e:
        logger.error(f"Error fetching DataFrame: {e}")
        return pd.DataFrame()



class AdminBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        self.initialize_files()

    def initialize_files(self):
        """Initialize necessary files"""
        # Initialize admin users file if it doesn't exist
        if not os.path.exists(ADMIN_USERS_FILE):
            default_admins = {
                "admin_usernames": [],
                "admin_user_ids": []
            }
            with open(ADMIN_USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_admins, f, ensure_ascii=False, indent=4)
            logger.info("Admin users file created")

        # Initialize questions file if it doesn't exist (optional but helpful)
        if not os.path.exists(QUESTIONS_FILE):
            default_questions = {
                "questions": [
                    "የአገልግሎት ጥራት እንዴት ነው?",
                    "የንጽህና ሁኔታ እንዴት ነው?",
                    "የዋጋ አሰጣጥ እንዴት ነው?"
                ]
            }
            with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_questions, f, ensure_ascii=False, indent=4)
            logger.info("Questions file created with defaults")

    def load_questions(self):
        """Load questions directly from Google Sheets"""
        try:
            client = get_client()
            if not client:
                logger.warning("Cannot load questions: Google Sheets client not available")
                return []

            sheet_obj = client.open_by_key(SHEET_ID).worksheet(QUESTIONS_SHEET_NAME)
            data = sheet_obj.col_values(1)  # Assuming first column stores questions
            if not data:
                return []

            # Remove header if present
            if data[0].strip().lower() == "question":
                return data[1:]
            return data
        except Exception as e:
            logger.error(f"Error loading questions from Google Sheets: {e}", exc_info=True)
            return []

    def save_questions(self, questions):
        """Save questions directly to Google Sheets"""
        try:
            client = get_client()
            if not client:
                logger.warning("Cannot save questions: Google Sheets client not available")
                return False

            sheet_obj = client.open_by_key(SHEET_ID).worksheet(QUESTIONS_SHEET_NAME)
            # Prepare data with header
            data = [["Question"]] + [[q] for q in questions]
            sheet_obj.update(f"A1:A{len(data)}", data)
            logger.info("Questions saved to Google Sheets successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving questions to Google Sheets: {e}", exc_info=True)
            return False

    def load_admin_users(self):
        """Load admin users from JSON file"""
        try:
            with open(ADMIN_USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading admin users: {e}")
            return {"admin_usernames": [], "admin_user_ids": []}

    def is_user_admin(self, user):
        """Check if user is admin by username or user ID"""
        admin_data = self.load_admin_users()
        user_username = user.username.lower() if user.username else ""
        return (user.id in admin_data["admin_user_ids"] or
                user_username in [u.lower() for u in admin_data["admin_usernames"]])

    def add_admin_user(self, user_id, username):
        """Add a new admin user"""
        admin_data = self.load_admin_users()

        if user_id not in admin_data["admin_user_ids"]:
            admin_data["admin_user_ids"].append(user_id)

        if username and username.lower() not in [u.lower() for u in admin_data["admin_usernames"]]:
            admin_data["admin_usernames"].append(username)

        try:
            with open(ADMIN_USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(admin_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"Error saving admin users: {e}")
            return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        welcome_text = (
            "👋 እንኳን ደህና መጡ!\n\n"
            "ይህ የአስተዳዳሪ ቦት ነው። የተጠቃሚዎችን መረጃ ለማስተዳደር እና ጥያቄዎችን ለመቀየር ያገለግላል።\n\n"
            "ለመጠቀም /login የሚለውን ይጫኑ ወይም ይጻፉ።"
        )
        await update.message.reply_text(welcome_text)

    async def login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Login command handler"""
        user = update.message.from_user

        # If already admin, show menu and stay in conversation
        if self.is_user_admin(user):
            await self.show_admin_panel(update, context)
            return ADMIN_MENU

        await update.message.reply_text(
            "🔐 እባክዎ የአስተዳዳሪ የይለፍ ቃል ያስገቡ።"
        )
        return AUTHENTICATE

    async def authenticate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Authenticate admin user"""
        user = update.message.from_user
        password_attempt = update.message.text

        if password_attempt == "admin123":  # Default admin password
            if self.add_admin_user(user.id, user.username):
                await update.message.reply_text(
                    "✅ እንኳን ደህና መጡ አዲስ አስተዳዳሪ!\n\n"
                    "አሁን የአስተዳዳሪ ፓነል መጠቀም ይችላሉ።"
                )
            await self.show_admin_panel(update, context)
            return ADMIN_MENU
        else:
            await update.message.reply_text(
                "❌ የተሳሳተ የይለፍ ቃል!\n\n"
                "እባክዎ ደግመው ይሞክሩ ወይም ከአስተዳዳሪ ያግኙ።"
            )
            return AUTHENTICATE

    async def show_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin panel"""
        keyboard = [['📊 መረጃ ለማውረድ', '❓ ጥያቄዎችን ለማሻሻል', '📊 የመረጃ ስታቲስቲክስ']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)

        await update.message.reply_text(
            "🔧 የአስተዳዳሪ ፓነል\n\n"
            "የሚከተሉትን ለመምረጥ ይችላሉ:",
            reply_markup=reply_markup
        )

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin panel handler (runs INSIDE the conversation)"""
        user = update.message.from_user
        if not self.is_user_admin(user):
            await update.message.reply_text("❌ አስተዳዳሪ መሆን አይችሉም!")
            return AUTHENTICATE

        command = update.message.text

        if command == '📊 መረጃ ለማውረድ':
            logger.info("User requested data download")
            file_path = sheet_to_excel_local()
            logger.info(f"sheet_to_excel_local returned: {file_path}")

            if not file_path or not os.path.exists(file_path):
                logger.error("Excel file not created or path invalid")
                await update.message.reply_text("❌ አሁን ምንም መረጃ አልተገኘም!")
                return ADMIN_MENU

            try:
                file_size = os.path.getsize(file_path)
                logger.info(f"Excel file exists: {file_path}, size: {file_size} bytes")

                with open(file_path, 'rb') as f:
                    logger.info("Sending Excel file to Telegram...")
                    await update.message.reply_document(
                        document=f,
                        filename="data.xlsx",
                        caption="📊 የተሰበሰበ መረጃ (Google Sheets)"
                    )
                    logger.info("Excel file sent successfully")

            except Exception as e:
                logger.error(f"Error sending Excel file: {e}", exc_info=True)
                await update.message.reply_text("❌ ፋይል ለመላክ ስህተት ተፈጥሯል!")

            finally:
                try:
                    os.remove(file_path)
                    logger.info(f"Temporary Excel file {file_path} deleted")
                except Exception as e:
                    logger.warning(f"Could not delete temp Excel file: {e}")

            return ADMIN_MENU


        elif command == '❓ ጥያቄዎችን ለማሻሻል':
            keyboard = [
                ['👀 ጥያቄዎችን ለመመልከት', '➕ ጥያቄ ለመጨመር'],
                ['✏️ ጥያቄ ለመቀየር', '🗑️ ጥያቄ ለመሰረዝ'],
                ['↩️ ወደ ኋላ']
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                "❓ የጥያቄ አስተዳደር\n\n"
                "የሚፈልጉትን አይነት ለውጥ ይምረጡ:",
                reply_markup=reply_markup
            )
            return EDIT_QUESTIONS

        elif command == '📊 የመረጃ ስታቲስቲክስ':
            try:
                df = get_dataframe()
                if df.empty:
                    await update.message.reply_text("❌ አስካሁን ምንም መረጃ አልተሰበሰበም!")
                    return ADMIN_MENU

                total_submissions = len(df)
                stats_text = f"📊 የመረጃ ስታቲስቲክስ:\n\n"
                stats_text += f"📝 አጠቃላይ መረጃዎች: {total_submissions}\n\n"

                questions = self.load_questions()
                for i, q in enumerate(questions):
                    col = f'Q{i+1}'
                    if col in df.columns:
                        try:
                            avg_rating = df[col].astype(float).mean()
                            stats_text += f"{i+1}. {q}\n   ⭐ አማካኝ ደረጃ: {avg_rating:.2f}/5\n\n"
                        except Exception:
                            pass

                await update.message.reply_text(stats_text)

            except Exception as e:
                logger.error(f"Error generating statistics: {e}")
                await update.message.reply_text("❌ የመረጃ ስታቲስቲክስ ለማውጣት አልተቻለም!")
            return ADMIN_MENU


        # Default: stay in menu
        await self.show_admin_panel(update, context)
        return ADMIN_MENU

    async def edit_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle question editing options (INSIDE conversation)"""
        user = update.message.from_user
        if not self.is_user_admin(user):
            await update.message.reply_text("❌ አስተዳዳሪ መሆን አይችሉም!")
            return AUTHENTICATE

        command = update.message.text
        questions = self.load_questions()

        if command == '👀 ጥያቄዎችን ለመመልከት':
            if not questions:
                await update.message.reply_text("❌ ምንም ጥያቄዎች አልተገኙም!")
            else:
                questions_text = "📋 ሁሉም ጥያቄዎች:\n\n"
                for i, q in enumerate(questions):
                    questions_text += f"{i+1}. {q}\n"
                await update.message.reply_text(questions_text)
            return EDIT_QUESTIONS

        elif command == '➕ ጥያቄ ለመጨመር':
            await update.message.reply_text(
                "➕ አዲስ ጥያቄ ለመጨመር\n\n"
                "እባክዎ አዲሱን ጥያቄ ያስገቡ:",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data['editing_mode'] = 'add'
            return NEW_QUESTION

        elif command == '✏️ ጥያቄ ለመቀየር':
            if not questions:
                await update.message.reply_text("❌ ምንም ጥያቄዎች አልተገኙም!")
                return EDIT_QUESTIONS

            keyboard = []
            for i, q in enumerate(questions):
                title = (q[:27] + '...') if len(q) > 30 else q
                keyboard.append([InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"edit_{i}")])

            keyboard.append([InlineKeyboardButton("❌ ስህተት", callback_data="cancel_edit")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "✏️ ጥያቄ ለመቀየር\n\n"
                "ለመቀየር የሚፈልጉትን ጥያቄ ይምረጡ:",
                reply_markup=reply_markup
            )
            return EDIT_QUESTIONS

        elif command == '🗑️ ጥያቄ ለመሰረዝ':
            if not questions:
                await update.message.reply_text("❌ ምንም ጥያቄዎች አልተገኙም!")
                return EDIT_QUESTIONS

            keyboard = []
            for i, q in enumerate(questions):
                title = (q[:27] + '...') if len(q) > 30 else q
                keyboard.append([InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"delete_{i}")])

            keyboard.append([InlineKeyboardButton("❌ ስህተት", callback_data="cancel_delete")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🗑️ ጥያቄ ለመሰረዝ\n\n"
                "ለመሰረዝ የሚፈልጉትን ጥያቄ ይምረጡ:",
                reply_markup=reply_markup
            )
            return EDIT_QUESTIONS

        elif command == '↩️ ወደ ኋላ':
            # Go back to admin menu (stay inside conversation)
            await self.show_admin_panel(update, context)
            return ADMIN_MENU

        else:
            await update.message.reply_text("❗ የመረጡት አማራጭ አይታወቅም።")
            return EDIT_QUESTIONS

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data
        questions = self.load_questions()

        if data.startswith("edit_"):
            index = int(data.split("_")[1])
            context.user_data['editing_index'] = index
            context.user_data['editing_mode'] = 'edit'

            await query.edit_message_text(
                f"✏️ ጥያቄ ለመቀየር\n\n"
                f"እባክዎ አዲስ ጥያቄ ያስገቡ ለ ጥያቄ #{index+1}:\n\n"
                f"አሁን ያለው: {questions[index]}"
            )
            return NEW_QUESTION

        elif data.startswith("delete_"):
            index = int(data.split("_")[1])
            context.user_data['deleting_index'] = index

            keyboard = [
                [InlineKeyboardButton("✅ አዎ ሰርዝ", callback_data="confirm_delete")],
                [InlineKeyboardButton("❌ አይሳሳት", callback_data="cancel_delete")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🗑️ ጥያቄ ለመሰረዝ\n\n"
                f"ይህን ጥያቄ ለመሰረዝ እርግጠኛ ነዎት?\n\n"
                f"{questions[index]}",
                reply_markup=reply_markup
            )
            return EDIT_QUESTIONS

        elif data == "confirm_delete":
            index = context.user_data.get('deleting_index')
            if index is not None and 0 <= index < len(questions):
                deleted_question = questions.pop(index)
                if self.save_questions(questions):
                    await query.edit_message_text(
                        f"✅ ጥያቄ ተሰርዟል:\n\n{deleted_question}"
                    )
                else:
                    await query.edit_message_text("❌ ጥያቄ ሲሰረዝ ስህተት ተፈጥሯል!")
            else:
                await query.edit_message_text("❌ ልክ ያልሆነ ጥያቄ መረጃ!")
            return await self.return_to_question_management(update, context)

        elif data == "cancel_delete" or data == "cancel_edit":
            await query.edit_message_text("❌ ስራው ተቋርጧል።")
            return await self.return_to_question_management(update, context)

        return EDIT_QUESTIONS

    async def return_to_question_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Return to question management menu"""
        keyboard = [
            ['👀 ጥያቄዎችን ለመመልከት', '➕ ጥያቄ ለመጨመር'],
            ['✏️ ጥያቄ ለመቀየር', '🗑️ ጥያቄ ለመሰረዝ'],
            ['↩️ ወደ ኋላ']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        if update.callback_query:
            await update.callback_query.message.reply_text(
                "❓ የጥያቄ አስተዳደር\n\n"
                "የሚፈልጉትን አይነት ለውጥ ይምረጡ:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "❓ የጥያቄ አስተዳደር\n\n"
                "የሚፈልጉትን አይነት ለውጥ ይምረጡ:",
                reply_markup=reply_markup
            )

        return EDIT_QUESTIONS

    async def handle_new_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new question input"""
        new_question = update.message.text
        questions = self.load_questions()
        editing_mode = context.user_data.get('editing_mode')

        if editing_mode == 'add':
            questions.append(new_question)
            if self.save_questions(questions):
                await update.message.reply_text("✅ አዲስ ጥያቄ ታክሏል!")
            else:
                await update.message.reply_text("❌ ጥያቄ ሲጨመር ስህተት ተፈጥሯል!")

        elif editing_mode == 'edit':
            index = context.user_data.get('editing_index')
            if index is not None and 0 <= index < len(questions):
                old_question = questions[index]
                questions[index] = new_question
                if self.save_questions(questions):
                    await update.message.reply_text(
                        f"✅ ጥያቄ ተቀይሯል!\n\n"
                        f"ከ: {old_question}\n"
                        f"ወደ: {new_question}"
                    )
                else:
                    await update.message.reply_text("❌ ጥያቄ ሲቀየር ስህተት ተፈጥሯል!")
            else:
                await update.message.reply_text("❌ ልክ ያልሆነ ጥያቄ መረጃ!")

        # Clear editing data
        context.user_data.pop('editing_mode', None)
        context.user_data.pop('editing_index', None)
        context.user_data.pop('deleting_index', None)

        return await self.return_to_question_management(update, context)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the conversation"""
        await update.message.reply_text(
            "❌ ስራው ተቋርጧል።\n\n"
            "ደግመው ለመጀመር /login ይጠቀሙ።",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    def setup_handlers(self):
        """Setup all handlers"""
        logger.info("Setting up bot handlers")
        admin_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('login', self.login)],
            states={
                AUTHENTICATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.authenticate),
                ],
                ADMIN_MENU: [
                    MessageHandler(filters.Regex('^(📊 መረጃ ለማውረድ|❓ ጥያቄዎችን ለማሻሻል|📊 የመረጃ ስታቲስቲክስ)$'), self.admin_panel),
                ],
                EDIT_QUESTIONS: [
                    MessageHandler(filters.Regex('^(👀 ጥያቄዎችን ለመመልከት|➕ ጥያቄ ለመጨመር|✏️ ጥያቄ ለመቀየር|🗑️ ጥያቄ ለመሰረዝ|↩️ ወደ ኋላ)$'), self.edit_questions),
                    CallbackQueryHandler(self.handle_callback_query),
                ],
                NEW_QUESTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_new_question),
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
            allow_reentry=True,
        )

        self.application.add_handler(admin_conv_handler)
        self.application.add_handler(CommandHandler('start', self.start))
        # ADD THIS: Handler for admin menu buttons outside conversation
        self.application.add_handler(MessageHandler(
            filters.Regex('^(📊 መረጃ ለማውረድ|❓ ጥያቄዎችን ለማሻሻል|📊 የመረጃ ስታቲስቲክስ)$') & ~filters.COMMAND,
            self.admin_panel_fallback
        ))
        
        logger.info("Handlers setup completed")

    async def admin_panel_fallback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin panel buttons when not in conversation"""
        user = update.message.from_user
        logger.info(f"Fallback handler for admin command: {update.message.text} from user {user.id}")
        
        if not self.is_user_admin(user):
            await update.message.reply_text("❌ አስተዳዳሪ መሆን አይችሉም! እባክዎ /login ይጠቀሙ።")
            return
        
        # Start conversation and handle the command
        await self.show_admin_panel(update, context)
        return await self.admin_panel(update, context)
    
    def run(self):
        """Run the bot"""
        print("Admin Bot is running... Press Ctrl+C to stop.")
        # self.application.run_polling()
        return self.application

def main():
    bot_token = os.getenv('ADMIN_BOT_TOKEN')
    if not bot_token:
        logger.error("ADMIN_BOT_TOKEN not found in environment variables")
        return
    bot = AdminBot(bot_token)
    # bot.run()
    return bot.application

if __name__ == '__main__':
    main()
