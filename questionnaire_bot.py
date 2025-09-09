import os
import logging
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)
from dotenv import load_dotenv
from datetime import datetime

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1HfK7_BYyewklYn32m82qteGgByzTTxA6_fovaDYdl74"
CREDS_FILE = "/etc/secrets/reflected-cycle-448109-p5-65cedb726569.json"

def get_client():
    """Authorize Google Sheets client from secret file"""
    credentials = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(credentials)
    return client


def append_to_sheet(user_id, user_data, ratings):
    client = get_client()
    sheet = client.open_by_key(SHEET_ID).sheet1

    # Always check the first row
    first_row = sheet.row_values(1)

    if not first_row or first_row[0] != "UserID":
        # Reset headers at row 1
        questions = QuestionnaireBot("").load_questions()
        headers = ["UserID", "Name", "Phone", "Timestamp"] + [f"Q{i+1}" for i in range(len(questions))]

        if first_row:
            # If data already exists in row 1, insert a new row above it
            sheet.insert_row(headers, 1)
        else:
            # If sheet is empty, just set headers
            sheet.append_row(headers)

    # Append the new submission
    row = [
        str(user_id),
        user_data.get("name"),
        user_data.get("phone"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ] + ratings

    sheet.append_row(row)


# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Conversation states
NAME, PHONE, RATINGS = range(3)

# File paths
# EXCEL_FILE = 'data.xlsx'
QUESTIONS_FILE = 'questions.json'

# Emojis for ratings
RATING_EMOJIS = ["😠", "😞", "😐", "🙂", "😄"]


class QuestionnaireBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
        # self.initialize_excel()
        logger.info("Bot initialized successfully")

    # def initialize_excel(self):
    #     """Create Excel file with headers if it doesn't exist"""
    #     logger.debug("Checking if Excel file exists...")
    #     if not os.path.exists(EXCEL_FILE):
    #         df = pd.DataFrame(columns=['UserID', 'Name', 'Phone', 'Timestamp'])
    #         questions = self.load_questions()
    #         for i, _ in enumerate(questions):
    #             df[f'Q{i+1}'] = None
    #         df.to_excel(EXCEL_FILE, index=False)
    #         logger.info("Excel file created with headers")
    #     else:
    #         logger.debug("Excel file already exists")

    def load_questions(self):
        """Load questions from JSON file"""
        logger.debug("Loading questions from JSON...")
        try:
            with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                questions = data.get('questions', [])
                logger.debug(f"Loaded {len(questions)} questions")
                return questions
        except Exception as e:
            logger.error(f"Error loading questions: {e}")
            return []

    # def has_user_submitted(self, user_id):
    #     try:
    #         if not os.path.exists(EXCEL_FILE):
    #             return False
    #         df = pd.read_excel(EXCEL_FILE)
    #         if "UserID" not in df.columns:
    #             return False
    #         df["UserID"] = df["UserID"].apply(lambda x: int(x) if pd.notnull(x) else 0)
    #         return int(user_id) in df["UserID"].values
    #     except Exception as e:
    #         logger.error(f"Error checking user submission: {e}")
    #         return False
    def has_user_submitted(self, user_id):
        """Check in Google Sheet if user already submitted"""
        try:
            client = get_client()
            sheet = client.open_by_key(SHEET_ID).sheet1
            data = sheet.get_all_records()  # list of dicts with headers as keys

            # If no data yet, user hasn't submitted
            if not data:
                return False

            # Check UserID column
            for row in data:
                if str(row.get("UserID")) == str(user_id):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking user submission in Google Sheet: {e}")
            return False



    # def save_to_excel(self, user_id: int, user_data: dict, ratings: list):
    #     """Save user data and ratings to Excel file"""
    #     logger.debug("Saving data to Excel...")
    #     try:
    #         df = pd.read_excel(EXCEL_FILE)

    #         new_row = {
    #             'UserID': str(user_id),
    #             'Name': user_data.get('name'),
    #             'Phone': user_data.get('phone'),
    #             'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #         }

    #         for i, rating in enumerate(ratings):
    #             new_row[f'Q{i+1}'] = rating

    #         df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    #         df.to_excel(EXCEL_FILE, index=False)
    #         logger.info(f"Saved new row for user {user_id}")

    #     except Exception as e:
    #         logger.error(f"Error saving to Excel: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the bot"""
        user = update.message.from_user
        logger.debug(f"/start received from user {user.id}")

        if self.has_user_submitted(user.id):
            await update.message.reply_text(
                "🙏 ይቅርታ! አስቀድመው ይህን ቃለ-መጠይቅ ሞልተዋል።",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.debug(f"User {user.id} blocked from resubmitting")
            return ConversationHandler.END

        # If user not submitted yet, start the form
        await update.message.reply_text(
            "👋 እንኳን ደህና መጡ!\n"
            "እባክዎ ሙሉ ስምዎን ያስገቡ:"
        )
        context.user_data["user_id"] = user.id
        return NAME


    async def start_form(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the form"""
        user = update.message.from_user
        logger.debug(f"Starting form for user {user.id} ({user.first_name})")

        if self.has_user_submitted(user.id):
            await update.message.reply_text(
                "🙏 ይቅርታ! አስቀድመው ይህን ቃለ-መጠይቅ ሞልተዋል።",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.debug(f"User {user.id} already submitted, blocking")
            return ConversationHandler.END

        context.user_data["user_id"] = user.id
        await update.message.reply_text(
            "📋 እባክዎ ሙሉ ስምዎን ያስገቡ:"
        )
        return NAME

    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug(f"Received name: {update.message.text}")
        context.user_data['name'] = update.message.text
        await update.message.reply_text("📞 እባክዎ ስልክ ቁጥርዎን ያስገቡ:")
        return PHONE

    async def get_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug(f"Received phone: {update.message.text}")
        context.user_data['phone'] = update.message.text

        context.user_data['ratings'] = []
        context.user_data['current_question'] = 0

        questions = self.load_questions()
        if not questions:
            await update.message.reply_text("❌ ምንም ጥያቄዎች አልተገኙም።")
            logger.error("No questions found in questions.json")
            return ConversationHandler.END

        reply_markup = ReplyKeyboardMarkup(
            [[emoji for emoji in RATING_EMOJIS]],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"✨ <b>Q1:</b> {questions[0]}",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.debug(f"Asking first question: {questions[0]}")
        return RATINGS

    async def handle_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        rating_text = update.message.text.strip()
        questions = self.load_questions()
        current_q = context.user_data['current_question']
        logger.debug(f"Received rating input: {rating_text}")

        if rating_text in RATING_EMOJIS:
            rating = RATING_EMOJIS.index(rating_text) + 1
            context.user_data['ratings'].append(rating)
            logger.debug(f"Stored rating {rating} for Q{current_q+1}")
        else:
            await update.message.reply_text("❌ እባክዎ ከታች ያሉትን ኢሞጂዎች ብቻ ይጠቀሙ።")
            logger.warning("Invalid rating input received")
            return RATINGS

        context.user_data['current_question'] += 1
        current_q = context.user_data['current_question']

        if current_q >= len(questions):
            append_to_sheet(
                context.user_data["user_id"],
                context.user_data,
                context.user_data['ratings']
            )
            await update.message.reply_text(
                "✅ እናመሰግናለን! ቃለ-መጠይቁን ጨርሰዋል። መረጃዎንም ተቀብለናል። 🎉",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.debug(f"Form completed for user {context.user_data['user_id']}")
            context.user_data.clear()
            return ConversationHandler.END

        reply_markup = ReplyKeyboardMarkup(
            [[emoji for emoji in RATING_EMOJIS]],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"✨ <b>Q{current_q+1}:</b> {questions[current_q]}",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.debug(f"Asking next question: {questions[current_q]}")
        return RATINGS

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug("Form cancelled by user")
        await update.message.reply_text(
            "❌ ቃለ-መጠይቁ ተቋርጧል።",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    def setup_handlers(self):
        form_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_name)],
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_phone)],
                RATINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_rating)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        self.application.add_handler(form_conv_handler)
        logger.debug("Handlers set up")

    def run(self):
        print("🚀 Questionnaire Bot is running...")
        # self.application.run_polling()
        return self.application


def main():
    token = os.getenv('QUESTIONNAIRE_BOT_TOKEN')
    if not token:
        logger.error("No bot token found in environment variables")
        return
    logger.info(f"Using bot token: {token[:6]}... (hidden for security)")
    bot = QuestionnaireBot(token)
    # bot.run()
    return bot.application


if __name__ == '__main__':
    main()
