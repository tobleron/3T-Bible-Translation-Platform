from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import sys

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)
driver.get("http://127.0.0.1:8765/chat")
time.sleep(3) # Wait for React to mount
textareas = driver.find_elements(By.TAG_NAME, "textarea")
for ta in textareas:
    print(f"ID: {ta.get_attribute('id')}")
    print(f"Class: {ta.get_attribute('class')}")
driver.quit()
