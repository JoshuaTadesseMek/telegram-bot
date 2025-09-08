import asyncio
from admin_bot import AdminBot
from questionnaire_bot import QuestionnaireBot


ADMIN_TOKEN = "8267449650:AAE70BkJJ5w5j5EbnC45gicwlX4wgCrCElY"
QUESTIONNAIRE_TOKEN = "8184833822:AAGZGQlNw4RM_VatbeXuvOJrdwZWEgFnylc"


async def run_bots():
    admin_bot = AdminBot(ADMIN_TOKEN)
    questionnaire_bot = QuestionnaireBot(QUESTIONNAIRE_TOKEN)

    # Initialize both
    await admin_bot.application.initialize()
    await questionnaire_bot.application.initialize()

    # Start both
    await admin_bot.application.start()
    await questionnaire_bot.application.start()

    # Start polling on both
    await admin_bot.application.updater.start_polling()
    await questionnaire_bot.application.updater.start_polling()

    print("✅ Both bots are now running...")

    # Keep running until interrupted
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Shutting down both bots...")
        await admin_bot.application.stop()
        await questionnaire_bot.application.stop()
        await admin_bot.application.shutdown()
        await questionnaire_bot.application.shutdown()


if __name__ == "__main__":
    asyncio.run(run_bots())
