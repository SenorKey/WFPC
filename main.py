from gui import WFPC
from app_controller import AppController

# Create the GUI window
app = WFPC()

# Create the controller and connect it to the GUI
controller = AppController(app)
app.set_controller(controller)

# Load any cached market data on startup
controller.load_cached_data()

# Start the application
app.mainloop()