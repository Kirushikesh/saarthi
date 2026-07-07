// Multilingual layer — pan-India per IDBI's Track 1 brief. The agent itself
// replies in whatever language the customer uses; this file localizes the
// shell: greetings, suggestion chips, input placeholder and speech lang codes.

export const LANGS = [
  { code: 'en', label: 'EN', name: 'English', native: 'English', bcp47: 'en-IN' },
  { code: 'hi', label: 'हिं', name: 'Hindi', native: 'हिंदी', bcp47: 'hi-IN' },
  { code: 'ta', label: 'த', name: 'Tamil', native: 'தமிழ்', bcp47: 'ta-IN' },
  { code: 'te', label: 'తె', name: 'Telugu', native: 'తెలుగు', bcp47: 'te-IN' },
  { code: 'kn', label: 'ಕ', name: 'Kannada', native: 'ಕನ್ನಡ', bcp47: 'kn-IN' },
  { code: 'bn', label: 'বাং', name: 'Bengali', native: 'বাংলা', bcp47: 'bn-IN' },
  { code: 'mr', label: 'म', name: 'Marathi', native: 'मराठी', bcp47: 'mr-IN' },
]

export const bcp47 = (code) => LANGS.find((l) => l.code === code)?.bcp47 || 'en-IN'

export const GREET = {
  en: (name) => `Namaste ${name}! I'm **Saarthi**, your personal wealth companion. Ask me about your portfolio, goals, or whether you can afford that next big step.`,
  hi: (name) => `नमस्ते ${name}! मैं **सारथी** हूँ, आपका व्यक्तिगत वेल्थ साथी। अपने निवेश, लक्ष्य या किसी बड़े खर्च की योजना के बारे में पूछिए।`,
  ta: (name) => `வணக்கம் ${name}! நான் **சாரதி**, உங்கள் தனிப்பட்ட செல்வத் துணை. உங்கள் முதலீடுகள், இலக்குகள் அல்லது பெரிய செலவுத் திட்டங்கள் பற்றிக் கேளுங்கள்.`,
  te: (name) => `నమస్తే ${name}! నేను **సారథి**, మీ వ్యక్తిగత సంపద తోడు. మీ పెట్టుబడులు, లక్ష్యాలు లేదా పెద్ద ఖర్చుల గురించి అడగండి.`,
  kn: (name) => `ನಮಸ್ತೆ ${name}! ನಾನು **ಸಾರಥಿ**, ನಿಮ್ಮ ವೈಯಕ್ತಿಕ ಸಂಪತ್ತು ಸಂಗಾತಿ. ನಿಮ್ಮ ಹೂಡಿಕೆಗಳು, ಗುರಿಗಳು ಅಥವಾ ದೊಡ್ಡ ಖರ್ಚಿನ ಬಗ್ಗೆ ಕೇಳಿ.`,
  bn: (name) => `নমস্কার ${name}! আমি **সারথি**, আপনার ব্যক্তিগত সম্পদ সঙ্গী। আপনার বিনিয়োগ, লক্ষ্য বা বড় খরচের পরিকল্পনা নিয়ে জিজ্ঞাসা করুন।`,
  mr: (name) => `नमस्कार ${name}! मी **सारथी**, तुमचा वैयक्तिक संपत्ती साथी. तुमच्या गुंतवणुकी, ध्येये किंवा मोठ्या खर्चाबद्दल विचारा.`,
}

export const SUGGESTIONS = {
  individual: {
    en: ['How are my investments doing?', 'Am I on track for retirement?', 'How much more tax can I save this year?', 'Can I afford a ₹50 lakh home loan for 20 years?', 'I want to buy term insurance'],
    hi: ['मेरे निवेश कैसे चल रहे हैं?', 'क्या मैं रिटायरमेंट के लिए तैयार हूँ?', 'क्या मैं 20 साल के लिए ₹50 लाख का होम लोन ले सकता हूँ?'],
    ta: ['என் முதலீடுகள் எப்படி உள்ளன?', 'ஓய்வுக்காலத்திற்கு நான் தயாரா?', '20 ஆண்டுகளுக்கு ₹50 லட்சம் வீட்டுக் கடன் வாங்க முடியுமா?'],
    te: ['నా పెట్టుబడులు ఎలా ఉన్నాయి?', 'రిటైర్మెంట్‌కు నేను సిద్ధంగా ఉన్నానా?', '20 ఏళ్లకు ₹50 లక్షల హోమ్ లోన్ తీసుకోగలనా?'],
    kn: ['ನನ್ನ ಹೂಡಿಕೆಗಳು ಹೇಗಿವೆ?', 'ನಿವೃತ್ತಿಗೆ ನಾನು ಸಿದ್ಧನಿದ್ದೇನೆಯೇ?', '20 ವರ್ಷಗಳಿಗೆ ₹50 ಲಕ್ಷ ಗೃಹ ಸಾಲ ಪಡೆಯಬಹುದೇ?'],
    bn: ['আমার বিনিয়োগ কেমন চলছে?', 'অবসরের জন্য আমি কি প্রস্তুত?', '২০ বছরের জন্য ₹৫০ লাখ হোম লোন নিতে পারব?'],
    mr: ['माझी गुंतवणूक कशी चालली आहे?', 'निवृत्तीसाठी मी तयार आहे का?', '20 वर्षांसाठी ₹50 लाखांचे गृहकर्ज घेऊ शकतो का?'],
  },
  household: {
    en: ['Can WE afford a ₹80 lakh home loan together?', 'How should we split savings for our home goal?', 'Are we on track to retire at 60?', 'Show our combined net worth'],
    hi: ['क्या हम मिलकर ₹80 लाख का होम लोन ले सकते हैं?', 'घर के लक्ष्य के लिए बचत कैसे बाँटें?'],
    ta: ['நாங்கள் சேர்ந்து ₹80 லட்சம் வீட்டுக் கடன் வாங்க முடியுமா?', 'வீட்டு இலக்குக்கான சேமிப்பை எப்படிப் பிரிப்பது?'],
    te: ['మేమిద్దరం కలిసి ₹80 లక్షల హోమ్ లోన్ తీసుకోగలమా?', 'ఇంటి లక్ష్యానికి పొదుపును ఎలా పంచుకోవాలి?'],
    kn: ['ನಾವು ಒಟ್ಟಿಗೆ ₹80 ಲಕ್ಷ ಗೃಹ ಸಾಲ ಪಡೆಯಬಹುದೇ?', 'ಮನೆ ಗುರಿಗಾಗಿ ಉಳಿತಾಯವನ್ನು ಹೇಗೆ ಹಂಚಬೇಕು?'],
    bn: ['আমরা কি একসাথে ₹৮০ লাখ হোম লোন নিতে পারি?', 'বাড়ির লক্ষ্যে সঞ্চয় কীভাবে ভাগ করব?'],
    mr: ['आपण मिळून ₹80 लाखांचे गृहकर्ज घेऊ शकतो का?', 'घराच्या ध्येयासाठी बचत कशी वाटायची?'],
  },
}

export const UI = {
  placeholder: {
    en: 'Ask about your money…', hi: 'अपना सवाल पूछें…',
    ta: 'உங்கள் பணத்தைப் பற்றிக் கேளுங்கள்…', te: 'మీ డబ్బు గురించి అడగండి…',
    kn: 'ನಿಮ್ಮ ಹಣದ ಬಗ್ಗೆ ಕೇಳಿ…', bn: 'আপনার টাকার বিষয়ে জিজ্ঞাসা করুন…',
    mr: 'तुमच्या पैशांबद्दल विचारा…',
  },
}

export const t = (map, lang) => map[lang] || map.en
