const express = require("express")
const { Pool } = require("pg")
const cors = require("cors")
const otpGenerator = require("otp-generator")
const nodemailer = require("nodemailer")
require('dotenv').config()

const port = 3000
const app = express()
app.use(cors())
app.use(express.json())

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

//CHECKS IF THE USER EXISTS IN THE DATABASE
app.post("/check-user", async(req, res)=>{
    try{
        const username = req.body.username

        const result = await pool.query(
            "SELECT 1 from voice_features WHERE username = $1 LIMIT 1", [username]
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
            "SELECT email from voice_features WHERE username = $1 LIMIT 1", [username]
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

app.post("/upload-details", async(req, res)=>{
    try{
        const username = req.body.username
        const email = req.body.email

        await pool.query(
            `INSERT INTO voice_features (username, email) VALUES ($1, $2)`,
            [username, email]
        )

        res.send("Details stored. Redirecting to the passphrase page...")
    } catch(err){
        console.log(err)
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