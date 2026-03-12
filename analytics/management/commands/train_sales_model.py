from django.core.management.base import BaseCommand
from analytics.ml.train_model import train_and_save_model
from analytics.ml.predict import run_predictions

class Command(BaseCommand):
    help = 'Trains the ML model for sales forecasting and generates predictions.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting the ML pipeline for sales forecasting..."))
        
        # Step 1: Train the model
        metrics = train_and_save_model()
        
        if metrics:
            self.stdout.write(self.style.SUCCESS("Model trained successfully."))
            self.stdout.write(f"Metrics: {metrics}")
        else:
            self.stdout.write(self.style.ERROR("Failed to train the model."))
            return
            
        # Step 2: Make predictions and save to the database
        self.stdout.write(self.style.SUCCESS("Generating predictions for the next year..."))
        try:
            run_predictions(metrics)
            self.stdout.write(self.style.SUCCESS("Predictions saved to the database successfully. Pipeline complete."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during prediction: {str(e)}"))
