#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

Servo rotateServo;  // Servo for rotation (D8)
Servo tiltServo;    // Servo for tilting (D9)
String inputString = "";
bool isSorting = false;
bool maintenanceMode = false;
unsigned long lastMaintenanceScrollTime = 0;
int maintenanceScrollPos = 0;

// LCD 1602 I2C address is commonly 0x27 or 0x3F
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Array of sorting jokes
const char* jokes[] = {
  "Sorting trash? Its   a waste of time!",
  "Why did the can    join recycling?   ",
  "To make new      friends!           ",
  "Im not trashy,    Im recyclable!    ",
  "Refuse to waste!                    ",
  "Keep calm and     sort on!          ",
  "Time to sort      things out!       ",
  "Waste wars: A new hope!             ",
  "Sort properly, or get the BIN Laden!"
};
const int NUM_JOKES = 8;

// Servo positions (must be between 0 and 180)
const int neutralPos = 90;    // D8 neutral position
const int nbioPos = 0;
const int bioPos = 90;
const int recycPos = 180;     // was 270 – corrected to valid servo range
const int tiltNeutralPos = 97;  // D9 neutral position

void setup() {
  rotateServo.attach(8);
  tiltServo.attach(9);
  Serial.begin(19200);
  lcd.begin(16, 2);  
  lcd.backlight();

  // Wait for gosort_ready signal
  lcd.setCursor(0, 0);
  lcd.print("GoSort - Booting");
  int dots = 0;
  unsigned long lastJokeTime = 0;
  unsigned long lastDotTime = 0;
  unsigned long lastScrollTime = 0;
  int currentJoke = 0;
  int scrollPos = 0;
  bool isScrolling = false;
  
  while (true) {
    if (Serial.available()) {
      String command = Serial.readString();
      if (command.indexOf("gosort_ready") != -1) {
        break;  // Exit the loop when gosort_ready is received
      }
    }
    
    unsigned long currentTime = millis();
    
    // Update dots every 500ms
    if (currentTime - lastDotTime >= 500) {
      lcd.setCursor(13, 0);
      switch(dots) {
        case 0: lcd.print("   "); break;
        case 1: lcd.print(".  "); break;
        case 2: lcd.print(".. "); break;
        case 3: lcd.print("..."); break;
      }
      dots = (dots + 1) % 4;
      lastDotTime = currentTime;
    }
    
    // Handle joke display and scrolling
    if (!isScrolling && currentTime - lastJokeTime >= 2000) {
      // Start new joke
      const char* currentJokeText = jokes[currentJoke];
      int jokeLength = strlen(currentJokeText);
      
      lcd.setCursor(0, 1);
      if (jokeLength <= 16) {
        // Short joke - display directly
        lcd.print(currentJokeText);
        currentJoke = (currentJoke + 1) % NUM_JOKES;
        lastJokeTime = currentTime;
      } else {
        // Long joke - start scrolling
        isScrolling = true;
        scrollPos = 0;
        lastScrollTime = currentTime;
      }
    }
    
    // Handle scrolling for long jokes
    if (isScrolling && currentTime - lastScrollTime >= 500) {
      const char* currentJokeText = jokes[currentJoke];
      int jokeLength = strlen(currentJokeText);
      
      lcd.setCursor(0, 1);
      if (scrollPos + 16 >= jokeLength) {
        // Reached end of joke
        isScrolling = false;
        currentJoke = (currentJoke + 1) % NUM_JOKES;
        lastJokeTime = currentTime;
      } else {
        // Continue scrolling
        char buffer[17];
        strncpy(buffer, &currentJokeText[scrollPos], 16);
        buffer[16] = '\0';
        lcd.print(buffer);
        scrollPos++;
        lastScrollTime = currentTime;
      }
    }
  }
  
  lcd.clear();
  Serial.println("Starting initialization...");
  lcd.setCursor(0, 0);
  lcd.print("Initializing...");

  // Sweep test with LCD output
  rotateServo.write(nbioPos);
  lcd.setCursor(0, 1);
  lcd.print("Non-Biodegradable");
  delay(1000);

  rotateServo.write(neutralPos);
  lcd.setCursor(0, 1);
  lcd.print("Neutral           ");
  delay(1000);

  rotateServo.write(bioPos);
  lcd.setCursor(0, 1);
  lcd.print("Biodegradable     ");
  delay(1000);

  rotateServo.write(recycPos);
  lcd.setCursor(0, 1);
  lcd.print("Recyclable        ");
  delay(1000);

  rotateServo.write(neutralPos);
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Ready           ");

  // Scroll "Go Sort by BeaBunda and Members"
  String message = "Go Sort by BeaBunda and Members   ";
  for (int i = 0; i < message.length() - 15; i++) {
    lcd.setCursor(0, 1);
    lcd.print(message.substring(i, i + 16));
    delay(300);
  }

  lcd.setCursor(0, 1);
  lcd.print("Awaiting Trash ");

  Serial.println("Initialization complete - Ready for sorting!");
}




void loop() {
  // Handle maintenance mode scrolling text
  if (maintenanceMode) {
    unsigned long currentTime = millis();
    if (currentTime - lastMaintenanceScrollTime >= 300) { // Scroll every 300ms
      String maintText = "Maintenance Mode... Standby   ";
      lcd.setCursor(0, 0);
      lcd.print(maintText.substring(maintenanceScrollPos, maintenanceScrollPos + 16));
      maintenanceScrollPos = (maintenanceScrollPos + 1) % (maintText.length() - 15);
      lastMaintenanceScrollTime = currentTime;
    }
  }

  while (Serial.available() && (!isSorting || maintenanceMode)) {
    char inChar = (char)Serial.read();
    inputString += inChar;

    if (inChar == '\n' || inChar == '\r') {
      inputString.trim();
      isSorting = !maintenanceMode; // Only set sorting flag if not in maintenance mode

      if (inputString == "nbio") {
        lcd.setCursor(0, 0);
        lcd.print("Sorting:          ");
        lcd.setCursor(0, 1);
        lcd.print("Non-Biodegradable");

        rotateServo.write(nbioPos);  // D8 rotate
        delay(500);
        tiltServo.write(150);    // D9 tilt
        delay(500);
        tiltServo.write(tiltNeutralPos);     // D9 back to neutral (85 yung sweet spot, tsaka na pag nalangisan na yung tilter, stalling kasi baka masunog)
        delay(500);
        rotateServo.write(neutralPos);  // D8 back to neutral
        delay(500);

        Serial.println("Moved to non-biodegradable position");
        Serial.println("ready");
      } 
      else if (inputString == "bio") {
        lcd.setCursor(0, 0);
        lcd.print("Sorting:          ");
        lcd.setCursor(0, 1);
        lcd.print("Biodegradable     ");

        rotateServo.write(bioPos);   // D8 rotate
        delay(500);
        tiltServo.write(150);    // D9 tilt
        delay(500);
        tiltServo.write(tiltNeutralPos);     // D9 back to neutral (85 yung sweet spot, tsaka na pag nalangisan na yung tilter, stalling kasi baka masunog)
        delay(500);
        rotateServo.write(neutralPos);  // D8 back to neutral
        delay(500);

        Serial.println("Moved to biodegradable position");
        Serial.println("ready");
      } 
      else if (inputString == "recyc") {
        lcd.setCursor(0, 0);
        lcd.print("Sorting:          ");
        lcd.setCursor(0, 1);
        lcd.print("Recyclable        ");

        rotateServo.write(recycPos); // D8 rotate
        delay(500);
        tiltServo.write(150);    // D9 tilt
        delay(500);
        tiltServo.write(tiltNeutralPos);     // D9 back to neutral (85 yung sweet spot, tsaka na pag nalangisan na yung tilter, stalling kasi baka masunog)
        delay(500);
        rotateServo.write(neutralPos);  // D8 back to neutral
        delay(500);

        Serial.println("Moved to recyclable position");
        Serial.println("ready");
      }
      // Maintenance mode commands
      else if (inputString == "maintmode") {
        maintenanceMode = true;
        maintenanceScrollPos = 0;
        lcd.clear();
        Serial.println("Entered maintenance mode");
      }
      else if (inputString == "maintend") {
        maintenanceMode = false;
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Ready             ");
        lcd.setCursor(0, 1);
        lcd.print("Awaiting command  ");
        Serial.println("Exited maintenance mode");
      }
      // Maintenance unclog command
      else if (maintenanceMode && inputString == "unclog") {
          lcd.setCursor(0, 1);
          lcd.print("Unclogging...    ");
          
          // Get D8's current position before unclogging
          int currentD8Position = rotateServo.read();  // Read current angle
          
          // Keep D8 at its current stuck position by not sending any new commands to it
          // Only operate D9 (tilt) for unclogging
          tiltServo.write(150);    // Tilt to maximum unclog position
          delay(3000);             // Hold for 3 seconds
          tiltServo.write(tiltNeutralPos); // Return tilt to neutral
          
          // No movement command sent to D8, so it stays where it was stuck
          
          lcd.setCursor(0, 1);
          lcd.print("Unclog at: ");
          lcd.print(currentD8Position);   // Show the position where unclog happened
          delay(2000);             // Show position for 2 seconds
          
          Serial.print("Unclog complete at position: ");
          Serial.println(currentD8Position);
          Serial.println("ready");
      }
      // Test sweep D8 only
      else if (maintenanceMode && inputString == "sweep1") {
          lcd.setCursor(0, 0);
          lcd.print("Test Sweep D8    ");
          lcd.setCursor(0, 1);
          lcd.print("Testing...       ");

          // Sweep D8 through all positions
          rotateServo.write(nbioPos);    // Go to non-bio (0°)
          delay(1000);
          rotateServo.write(bioPos);     // Go to bio (90°)
          delay(1000);
          rotateServo.write(recycPos);   // Go to recyclable (180°)
          delay(1000);
          rotateServo.write(neutralPos); // Return to neutral (90°)
          
          Serial.println("D8 sweep test complete");
          Serial.println("ready");
      }
      // Test sweep both servos
      else if (maintenanceMode && inputString == "sweep2") {
          lcd.setCursor(0, 0);
          lcd.print("Full Sweep Test  ");
          lcd.setCursor(0, 1);
          lcd.print("Testing...       ");

          // Set D9 to maintenance position
          tiltServo.write(150);
          delay(1000);

          // Sweep D8 through all positions
          rotateServo.write(nbioPos);    // Go to non-bio (0°)
          delay(1000);
          rotateServo.write(bioPos);     // Go to bio (90°)
          delay(1000);
          rotateServo.write(recycPos);   // Go to recyclable (180°)
          delay(1000);
          
          // Return both to neutral
          rotateServo.write(neutralPos); // D8 to neutral (90°)
          tiltServo.write(tiltNeutralPos);  // D9 to neutral (85°)
          
          Serial.println("Full sweep test complete");
          Serial.println("ready");
      }

      // Reset to "Ready"
      lcd.setCursor(0, 0);
      lcd.print("Ready             ");
      lcd.setCursor(0, 1);
      lcd.print("Awaiting command  ");
      inputString = "";
      isSorting = false;
    }
  }
}
