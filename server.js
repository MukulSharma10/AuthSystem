const express = require("express")
const multer = require("multer")
const { Pool } = require("pg")
const cors = require("cors")
const crypto = require("crypto")
const {spawn} = require("child_process")
const fs = require("fs")
const path = require("path")
const {execSync} = require("child_process")
const otpGenerator = require("otp-generator")
const nodemailer = require("nodemailer")
require('dotenv').config()

const port = 3000
const app = express()
app.use(cors())
app.use(express.json())

const upload = multer()

const SECRET_KEY = crypto
.createHash("sha256")
.update("my_super_secret_key")
.digest()

//DEFINING PGCLIENT POOL TO CONNECT TO THE DATABASE
const pool = new Pool({
    user: process.env.PGUSER,
    password: process.env.PGPASSWORD,
    host: process.env.PGHOST,
    port: process.env.PGPORT,
    database: process.env.PGDATABASE
})

//DELETES OTPs EVERY 60 SECONDS
pool.connect()
.then(() => {
    console.log('Connected to PostgreSQL')

    setInterval(async() => {
        try {
            await pool.query(
                "DELETE FROM otp_codes WHERE created_at < NOW() - INTERVAL '5 minutes' "
            )
            console.log('Expired OTPs cleaned')
        } catch(err){
            console.error('Error cleaning OTPs: ', err)
        }
    }, 60000)
})

//AUDIO ENCRYPTION FUNCTION
function encrypt(buffer) {
    const iv = crypto.randomBytes(16)
    const cipher = crypto.createCipheriv("aes-256-cbc", SECRET_KEY, iv)

    const encrypted = Buffer.concat([cipher.update(buffer), cipher.final()])

    return Buffer.concat([iv, encrypted])
}

//AUDIO DECRYPTION FUNCTION
function decrypt(buffer){
    const iv = buffer.slice(0, 16)
    const encyptedData = buffer.slice(16)

    const decipher = crypto.createDecipheriv("aes-256-cbc", SECRET_KEY, iv)
    return Buffer.concat([decipher.update(encyptedData), decipher.final()])
}

//UPLOADING AUDIO FILE TO THE DATABASE
app.post('/upload', upload.single("audio"), async (req, res)=>{
    try{
        const username = req.body.username
        const email = req.body.email
        const audioBuffer = req.file.buffer

        if(!username || !email){
            return res.status(400).send("Missing username or email")
        }

        const encryptedAudio = encrypt(audioBuffer)

        await pool.query(
            "INSERT INTO recordings (username, email, audio_data) VALUES ($1,$2,$3)",
            [username, email, encryptedAudio]
        )

        res.send("User registered & Audio Encrypted!")
    } catch(err){
        console.error(err)
        res.status(500).send("Error")
    }
})

//CHECKS IF THE USER EXISTS IN THE DATABASE
app.post("/check-user", async(req, res)=>{
    try{
        const username = req.body.username

        const result = await pool.query(
            "SELECT 1 from recordings WHERE username = $1 LIMIT 1", [username]
        )

        if(result.rows.length === 0){
            res.send("User does not exist")
        } else{
            res.send("User exists")
        }
    } catch(err){
        console.error(err)
        res.status(500).send("Error")
    }
})

app.post("/find-email", async(req, res)=>{
    try{
        const username = req.body.username

        const result = await pool.query(
            "SELECT email from recordings WHERE username = $1 LIMIT 1", [username]
        )

        if(result.rows.length === 0){
            res.send("User does not exist")
        } else{
            res.send(result.rows[0]['email'])
        }
    } catch(err){
        console.log(err)
        res.status(500).send("Error")
    }
})

//HANDLES LOGIN REQUESTS
app.post('/login', upload.single('audio'), async(req, res)=>{
    try{
        const username = req.body.username

        const result = await pool.query(
            "SELECT audio_data FROM recordings WHERE username = $1 LIMIT 1", [username]
        )

        if(result.rows.length === 0){
            return res.send("User does not exist!")
        }

        //Decrypting stored audios
        const encryptedBuffer = result.rows[0].audio_data
        const decryptAudio = decrypt(encryptedBuffer)

        //Saving both registered and login files temporarily
        const regPath = path.join(__dirname, "registered.wav")
        fs.writeFileSync(regPath, decryptAudio)

        const rawPath = path.join(__dirname, "login_raw.webm")
        fs.writeFileSync(rawPath, req.file.buffer)

        const wavPath = path.join(__dirname, "login.wav")

        //Resampling the recorded audio file using ffmpeg
        execSync(`ffmpeg -y -i "${rawPath}" -ar 16000 -ac 1 "${wavPath}"`)

        console.log("1st PART WORKING FINE!!!")
        //Python comparison engine
        const pythonScript = path.join(__dirname, "compare.py")
        const python = spawn("python", [
            pythonScript,
            regPath, 
            wavPath
        ])

        let pythonOutput = ""

        python.stdout.on("data", (data)=>{
            pythonOutput += data.toString().trim()
        })

        python.stderr.on("data", (err)=>{
            console.error("Python Error:", err.toString())
        })

        console.log("2nd PART WORKING FINE!!!")

        python.on("close", (code)=>{
            const output = pythonOutput.trim()
            
            if(code === 0 && output === "MATCH"){
                res.send("Login success!")
            } else if(code === 0){
                res.send("Voice not matched. Try Again!")
            } else {
                res.status(500).send("Comparison failed")
            }
        })

        console.log("WORKING FINE!!!")
    } catch(err){
        console.log(err)
        console.log("THERE IS AN ERROR IN THIS CODE")
        res.status(500).send("Error")
    }
})

//ROUTE TO SEND OTPs TO USER'S EMAIL
app.post('/generate-otp', async(req, res) => {
    const email = req.body.email || req.body.emailAddress

    if(!email){
        return res.status(400).send('Missing email address')
    }

    //GENERATING ACTUAL OTP
    const otp = otpGenerator.generate(6, {
        digits: true,
        lowerCaseAlphabets: false,
        upperCaseAlphabets: false,
        specialChars: false
    })

    try {
        await pool.query(
            `INSERT INTO otp_codes (email, otp) VALUES ($1, $2)`,
            [email, otp]
        );

        const transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: {
                user: process.env.EMAILUSER,
                pass: process.env.EMAILPASSWORD
            }
        })

        await transporter.sendMail({
            from: 'mukulsharma528491@gmail.com',
            to: email,
            subject: `Verification for passphrase reset`,
            text: `Your OTP is ${otp}`
        })

        res.status(200).send('OTP sent successfully')
        console.log('SUCCESS!')
    } catch(error) {
        console.log(error)
        res.status(500).send('Error sending OTP')
    }
})

//ROUTE TO VERIFY OTPs AGAINST THE USER
app.post('/verify-otp', async(req, res) =>{
    
    const { email, otp } = req.body

    try{
        const result = await pool.query(
            `SELECT * FROM otp_codes WHERE email = $1 AND otp = $2 ORDER BY created_at DESC LIMIT 1`,
            [email, otp]
        )

        if(result.rows.length > 0){
            res.status(200).send('OTP verified successfully')
        } else {
            res.status(400).send('Invalid OTP')
        }
    } catch(error) {
        console.log(error)
        res.status(500).send('Error verifying OTP')
    }
})


app.listen(port, ()=> console.log(`Server running on port ${port}`))