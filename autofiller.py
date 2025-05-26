import os
import time
import pickle
from typing import Dict, Any
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import Select
from models import FormData
import logging
from ast import literal_eval

SUBMIT = literal_eval(os.getenv("SUBMIT_FORM", "False"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FormAutofiller:
    """Enhanced class to autofill the travel form using Selenium with async support."""

    def __init__(self, form_url: str, login_url: str, cookie_path: str = "cookies.pkl"):
        self.form_url = form_url
        self.login_url = login_url
        self.cookie_path = cookie_path
        self.driver = None

        # Load environment variables
        load_dotenv()
        self.username = os.getenv("LOGIN_USERNAME")
        self.password = os.getenv("LOGIN_PASSWORD")

        if not self.username or not self.password:
            raise Exception("LOGIN_USERNAME or LOGIN_PASSWORD not set in .env")

    def _setup_driver(self):
        """Setup Chrome driver with options."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), 
            options=chrome_options
        )

    def login(self) -> bool:
        """Perform login or load cookies if available."""
        try:
            if os.path.exists(self.cookie_path):
                logger.info("Loading cookies...")
                self.driver.get("https://adventurescare.com")
                with open(self.cookie_path, "rb") as f:
                    cookies = pickle.load(f)
                for cookie in cookies:
                    self.driver.add_cookie(cookie)
                self.driver.refresh()
                self.driver.get(self.form_url)
                if "login" not in self.driver.current_url.lower():
                    logger.info("Logged in using cookies")
                    return True
                else:
                    logger.info("Cookies expired or invalid. Re-authenticating...")

            # Perform login manually
            self.driver.get(self.login_url)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "email")))
            self.driver.find_element(By.NAME, "email").send_keys(self.username)
            self.driver.find_element(By.NAME, "password").send_keys(self.password)
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()

            # Wait until redirected to the form or dashboard
            WebDriverWait(self.driver, 10).until(lambda d: "login" not in d.current_url.lower())
            logger.info("Logged in successfully")

            # Save cookies
            cookies = self.driver.get_cookies()
            with open(self.cookie_path, "wb") as f:
                pickle.dump(cookies, f)
            logger.info("Cookies saved")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def load_form(self) -> bool:
        """Load the form page."""
        try:
            self.driver.get(self.form_url)
            logger.info("Form page loaded")
            return True
        except Exception as e:
            logger.error(f"Failed to load form: {e}")
            return False

    def fill_form(self, data: Dict[str, Any]) -> bool:
        """Fill the form with the given data."""
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/div[2]/div[2]/div/div[2]/div/div/div[1]/ul/li[2]/a"))
            )
            self.driver.find_element(By.XPATH, '/html/body/div[2]/div[2]/div/div[2]/div/div/div[1]/ul/li[2]/a').click()
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "nationality"))
            )
            
            # Fill dropdown fields
            self.select_dropdown("nationality", data["nationality"])
            self.select_dropdown("travel_from", data["travel_from"])
            self.select_dropdown("travel_to", "Nepal")
            self.select_dropdown("package_id", data["package_id"])

            # Fill date fields
            start_date_elem = self.driver.find_element(By.NAME, "start_date")
            self.driver.execute_script(f"arguments[0].value = '{data['start_date']}'", start_date_elem)

            end_date_elem = self.driver.find_element(By.NAME, "end_date")
            self.driver.execute_script(f"arguments[0].value = '{data['end_date']}'", end_date_elem)

            dob_elem = self.driver.find_element(By.NAME, "dob")
            self.driver.execute_script(f"arguments[0].value = '{data['dob']}'", dob_elem)

            # Fill text fields
            self.driver.find_element(By.NAME, "surname").send_keys(data["surname"])
            self.driver.find_element(By.NAME, "given_name").send_keys(data["given_name"])
            self.driver.find_element(By.NAME, "phone_number").send_keys(data["phone_number"])
            self.driver.find_element(By.NAME, "email").send_keys(data["email"])
            self.driver.find_element(By.NAME, "address").send_keys(data["address"])
            self.driver.find_element(By.NAME, "emergency_contact").send_keys(data["emergency_contact"])
            self.driver.find_element(By.NAME, "passport_no").send_keys(data["passport_no"])

            # Upload files if provided
            if data.get("profile_image_path"):
                self.driver.find_element(By.NAME, "profile_image").send_keys("/app/"+data["profile_image_path"])
            if data.get("passport_image_path"):
                self.driver.find_element(By.NAME, "passport_image").send_keys("/app/"+data["passport_image_path"])

            logger.info("Form filled successfully")
            return True

        except Exception as e:
            logger.error(f"Error filling form: {e}")
            return False

    def select_dropdown(self, name: str, value: str) -> bool:
        """Select a value from a dropdown menu."""
        try:
            dropdown = self.driver.find_element(By.NAME, name)
            select = Select(dropdown)
            select.select_by_visible_text(value)
            return True
        except Exception as e:
            logger.warning(f"Standard selection failed, trying alternative approach: {e}")
            
        try:
            dropdown = self.driver.find_element(By.NAME, name)
            self.driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
            
            select2_container = self.driver.find_element(
                By.XPATH, f"//select[@name='{name}']/following-sibling::span[contains(@class, 'select2-container')]"
            )
            if select2_container:
                select2_container.click()
            else:
                dropdown.click()
            
            time.sleep(1)
            
            option = self.driver.find_element(
                By.XPATH, f"//li[contains(@class, 'select2-results__option') and text()='{value}']"
            )
            option.click()
            return True
        except Exception as e:
            try:
                logger.warning(f"Alternative selection failed, trying JavaScript approach: {e}")
                script = f"""
                var select = document.getElementsByName('{name}')[0];
                for (var i = 0; i < select.options.length; i++) {{
                    if (select.options[i].text === '{value}') {{
                        select.selectedIndex = i;
                        var event = new Event('change');
                        select.dispatchEvent(event);
                        break;
                    }}
                }}
                """
                self.driver.execute_script(script)
                return True
            except Exception as e:
                logger.error(f"Error selecting dropdown {name} with value {value}: {e}")
                return False

    def submit_form(self) -> bool:
        """Submit the form."""
        try:
            if SUBMIT:
                submit_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
                submit_button.click()
            logger.info("Form submitted successfully")
            return True
        except Exception as e:
            logger.error(f"Error submitting form: {e}")
            return False

    def close(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")

    async def process_form(self, form_data: FormData) -> bool:
        """Process the entire form filling workflow."""
        try:
            self._setup_driver()
            
            if not self.login():
                return False
                
            if not self.load_form():
                return False
                
            if not self.fill_form(form_data.dict()):
                return False
                
            time.sleep(2)  # Wait before submission
            
            if not self.submit_form():
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error processing form: {e}")
            return False
        finally:
            self.close()
