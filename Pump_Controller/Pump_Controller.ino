#define CMDSIZE 30

#define PUMP_OFF_TIME_MAX 600000UL
#define PUMP_START 7 //active as low output
#define VALVE_OPEN 9
#define PUMP_DIR 8
#define PUMP_SPEED 5
#define PUMP_ALARM 3

//For driving pumps
//Array of stepper steps
uint8_t steps[] = {
    0b00001001,
    0b00000001,
    0b00000011,
    0b00000010,
    0b00000110,
    0b00000100,
    0b00001100,
    0b00001000
};

int nstep = 0;

//Buffer for holding input commands
char cbuff[CMDSIZE];
uint8_t clen;

int speed = 0;

bool pump_off_flag = false;
unsigned long pump_off_time;

void setup() {
  //Clamp motor
  DDRC = 0x0F;

  pinMode(PUMP_SPEED, OUTPUT);
  Serial.begin(115200);

  pinMode(VALVE_OPEN, INPUT_PULLUP);
  pinMode(PUMP_ALARM, INPUT_PULLUP);

  release();

  //turn pump on to 50%
  analogWrite(PUMP_SPEED, (int) map(50,0,100,0,255));
  delay(10);
  digitalWrite(PUMP_START, LOW);
  pinMode(PUMP_START, OUTPUT);

}

void loop() {
  if(Serial.available() > 0){
    parsecmd();
  }
  if(pump_off_flag && (millis() - pump_off_time > PUMP_OFF_TIME_MAX)){
    Serial.println("Force Restarting Pump");
    Serial.println("Starting Motor");
    release();
    delay(10);
    digitalWrite(PUMP_START, LOW);
    pinMode(PUMP_START, OUTPUT);
    pump_off_flag = false;
  }
}

//Parse an incoming command
void parsecmd() {
  delay(50);
  int i = 0;
  clen = 0;
  while(Serial.available() && i < CMDSIZE){
    cbuff[i] = Serial.read();
    if(cbuff[i] == ' '){
      clen = i + 1;
      break;
    }
    i++;
  }
  clen = i;
  
  //parse the command
  if(command_is("setdir")){
    int direction = Serial.parseInt(SKIP_NONE, 50);
    digitalWrite(PUMP_DIR, LOW); //don't blow up the pump
    if(direction == 0) {
      pinMode(PUMP_DIR, OUTPUT);
      Serial.println("Setting Direction to CCW");
    }else {
      pinMode(PUMP_DIR, INPUT);
      Serial.println("Setting Direction to CW");
    }
  }

  else if(command_is("setspeed")){
    speed = Serial.parseInt(SKIP_NONE, 50);
    analogWrite(PUMP_SPEED, (int) map(speed,0,100,0,255));
    Serial.print("Setting Speed to ");
    Serial.println(speed);
  }

  else if(command_is("start")){
    Serial.println("Starting Motor");
    release();
    delay(10);
    start_pump();
    pump_off_flag = false;
  }

  else if(command_is("stop")){
    Serial.println("Stopping Motor");
    stop_pump();
    delay(10);
    clamp();

    //Start a timer to prevent 
    pump_off_flag = true;
    pump_off_time = millis();
  }

  else if(command_is("getspeed")){
    Serial.println(speed);
  }

  else if(command_is("getalarm")){
    bool alm = digitalRead(PUMP_ALARM);
    if(alm){
      Serial.println("Alarm!");
    }else{
      Serial.println("Safe");
    }
  }

  cbuff[0] = 0;

}

void printcmd(){
  Serial.println(clen);
  for(int i = 0; i < clen; i++){
    if(cbuff[i] != 0) Serial.print(cbuff[i]);
  }
  Serial.println();
}

bool command_is(String cmd){
  if (clen == 0) return false;
  for(int i = 0; i < clen; i++){
    if(cmd.charAt(i) != cbuff[i]) return false;
  }
  return true;
}

void empty(){
    while(Serial.available()) Serial.read();
}

void release(){
  digitalWrite(PUMP_START, LOW);
  pinMode(PUMP_START, OUTPUT);

  if(!digitalRead(VALVE_OPEN)){ //back off
    while(!digitalRead(VALVE_OPEN)){
        nstep = nstep - 1;
        PORTC = steps[nstep & 0x07];
        delay(1);
    }

    for(int i = 0; i < 400; i++){
        nstep = nstep - 1;
        PORTC = steps[nstep & 0x07];
        delay(1);
    }
    PORTC = 0x00;
  }
  while(digitalRead(VALVE_OPEN)){
      nstep = nstep + 1;
      PORTC = steps[nstep & 0x07];
      delay(1);
  }
  PORTC = 0x00;
  pinMode(PUMP_START, OUTPUT); //Turn the pump off again
}
 
void clamp(){
  if(!pump_off_flag){
    for(int i = 0; i < 13000; i++){
        nstep = nstep - 1;
        PORTC = steps[nstep & 0x07];
        delay(1);
    }
    PORTC = 0x00;    
  }

}

void start_pump(){
    digitalWrite(PUMP_START, LOW);
    pinMode(PUMP_START, OUTPUT);
}

void stop_pump(){
    digitalWrite(PUMP_START, HIGH);
    pinMode(PUMP_START, INPUT);
}


