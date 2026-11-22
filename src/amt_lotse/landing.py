"""The landing page around the tool: hero, "how it works", features, and the facts card of a result.

Everything here is plain HTML built from fixed texts and checked facts (no model output), in 8 languages.
"""

from datetime import date
from html import escape

from amt_lotse.cli import RTL_LANGUAGES
from amt_lotse.pipeline import CARD, Analysis, _euro
from amt_lotse.speak import say_date

LOGO = """<svg viewBox="0 0 48 48" aria-hidden="true" focusable="false"><rect width="48" height="48" rx="13" fill="#1f5fd1"/>
<rect x="12" y="9" width="21" height="28" rx="3.5" fill="#fff"/><rect x="16" y="15" width="13" height="2.6" rx="1.3" fill="#c7d6f5"/>
<rect x="16" y="20.5" width="9" height="2.6" rx="1.3" fill="#c7d6f5"/><rect x="16" y="26" width="13" height="2.6" rx="1.3" fill="#c7d6f5"/>
<circle cx="33" cy="33" r="9" fill="#12a150" stroke="#1f5fd1" stroke-width="2.5"/><path d="M28.8 33.2l3 3 5.4-6" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

# A letter, the key line marked, a speech bubble (read aloud) and a calendar badge (the deadline).
HERO_ART = """<svg class="art" viewBox="0 0 340 300" aria-hidden="true" focusable="false">
<defs><linearGradient id="amt-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#dfe9ff"/><stop offset="1" stop-color="#f3f7ff"/></linearGradient>
<filter id="amt-s" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#0b2a6b" flood-opacity=".18"/></filter></defs>
<circle cx="175" cy="150" r="128" fill="url(#amt-g)"/>
<g transform="rotate(-6 150 150)" filter="url(#amt-s)"><rect x="78" y="48" width="150" height="200" rx="14" fill="#fff"/>
<rect x="98" y="72" width="62" height="9" rx="4.5" fill="#1f5fd1"/><rect x="98" y="96" width="108" height="7" rx="3.5" fill="#d5def0"/>
<rect x="98" y="112" width="92" height="7" rx="3.5" fill="#d5def0"/><rect x="92" y="128" width="122" height="20" rx="6" fill="#ffd86b" opacity=".75"/>
<rect x="98" y="134.5" width="100" height="7" rx="3.5" fill="#7a5600"/><rect x="98" y="160" width="108" height="7" rx="3.5" fill="#d5def0"/>
<rect x="98" y="176" width="70" height="7" rx="3.5" fill="#d5def0"/><rect x="98" y="206" width="48" height="7" rx="3.5" fill="#d5def0"/></g>
<g filter="url(#amt-s)"><path d="M218 54h86a14 14 0 0 1 14 14v42a14 14 0 0 1-14 14h-52l-18 16v-16h-16a14 14 0 0 1-14-14V68a14 14 0 0 1 14-14z" fill="#1f5fd1"/>
<path d="M232 80h9l12-10v38l-12-10h-9z" fill="#fff"/><path d="M262 78q8 11 0 22M272 71q14 18 0 36" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/></g>
<g filter="url(#amt-s)"><rect x="232" y="172" width="86" height="86" rx="16" fill="#fff"/><rect x="232" y="172" width="86" height="26" rx="13" fill="#e5484d"/>
<rect x="232" y="186" width="86" height="12" fill="#e5484d"/><circle cx="254" cy="172" r="4" fill="#fff"/><circle cx="296" cy="172" r="4" fill="#fff"/>
<path d="M256 228l13 13 25-28" fill="none" stroke="#12a150" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/></g>
</svg>"""

ICONS = {"lock": "🔒", "check": "✅", "eye": "👁️", "pen": "✍️"}

# Example letters (fictional): office name stays German, as on the envelope; the hint is translated.
EXAMPLE_OFFICES = ["Jobcenter", "Mahnung", "Finanzamt", "Krankenkasse"]

TEXT = {
    "en": {
        "eyebrow": "Your guide through German paperwork",
        "tagline": "Understand every letter from German offices.",
        "lead": "Take a photo. Amt-Lotse tells you in your language what the letter wants, by when and how much — and reads it aloud.",
        "badges": ["AI on this computer", "8 languages", "Reads aloud", "Ask by voice"],
        "how_h": "How it works",
        "how": [("Photo or file", "Photograph the letter with your phone, or choose a PDF."),
                ("A clear answer", "What to do, the deadline and the amount — plus a calendar entry."),
                ("Listen and ask", "Hear it read aloud and ask your questions by voice.")],
        "feat_h": "Made for the people who need it most",
        "feats": [("lock", "Private", "No cloud AI: the letter is read and explained on this computer."),
                  ("check", "Numbers you can trust", "Deadlines and amounts are checked against the letter, never invented."),
                  ("eye", "Accessible", "Large text, high contrast, works with screen readers."),
                  ("pen", "Reply in German", "Writes a polite answer for you to check and send.")],
        "or_file": "or choose a file (photo, PDF, text)",
        "drop": "Drop the letter here or click to choose",
        "again": "🔄 Explain again in the chosen language",
        "expl_h": "What the letter means", "facts_h": "The facts at a glance",
        "examples": ["appointment", "payment reminder", "tax office", "health insurance"],
        "badge_cloud": "Private AI, no AI company", "private_cloud": "No AI company: the AI runs on a private computer, reached over an encrypted connection.",
        "open_app": 'Open Amt-Lotse', "checking": 'Checking whether the AI server is on …',
        "ai_on": "AI ready", "ai_off_h": "The AI server is off",
        "ai_off": "The computer that runs the AI is switched off right now. Letters can be explained again as soon as it is on. Please try again later.",
    },
    "fr": {
        "eyebrow": "Votre guide dans les courriers administratifs allemands",
        "tagline": "Comprenez chaque lettre des administrations allemandes.",
        "lead": "Prenez une photo. Amt-Lotse vous dit dans votre langue ce que la lettre demande, pour quand et combien — et vous la lit à voix haute.",
        "badges": ["IA sur cet ordinateur", "8 langues", "Lecture à voix haute", "Questions à la voix"],
        "how_h": "Comment ça marche",
        "how": [("Photo ou fichier", "Photographiez la lettre avec votre téléphone, ou choisissez un PDF."),
                ("Une réponse claire", "Quoi faire, la date limite et le montant — et une entrée d'agenda."),
                ("Écoutez et demandez", "Écoutez-la à voix haute et posez vos questions à la voix.")],
        "feat_h": "Conçu pour ceux qui en ont le plus besoin",
        "feats": [("lock", "Privé", "Pas d'IA dans le cloud : la lettre est lue et expliquée sur cet ordinateur."),
                  ("check", "Des chiffres fiables", "Dates et montants sont vérifiés dans la lettre, jamais inventés."),
                  ("eye", "Accessible", "Grand texte, contraste élevé, compatible avec les lecteurs d'écran."),
                  ("pen", "Réponse en allemand", "Rédige une réponse polie que vous vérifiez et envoyez.")],
        "or_file": "ou choisissez un fichier (photo, PDF, texte)",
        "drop": "Déposez la lettre ici ou cliquez pour choisir",
        "again": "🔄 Expliquer à nouveau dans la langue choisie",
        "expl_h": "Ce que dit la lettre", "facts_h": "L'essentiel en un coup d'œil",
        "examples": ["rendez-vous", "rappel de paiement", "impôts", "assurance maladie"],
        "badge_cloud": "IA privée, sans entreprise d'IA", "private_cloud": "Aucune entreprise d'IA : l'IA tourne sur un ordinateur privé, joint par une connexion chiffrée.",
        "open_app": 'Ouvrir Amt-Lotse', "checking": "Vérification : le serveur d'IA est-il allumé ? …",
        "ai_on": "IA prête", "ai_off_h": "Le serveur d'IA est éteint",
        "ai_off": "L'ordinateur qui fait tourner l'IA est éteint pour le moment. Les lettres pourront être expliquées dès qu'il sera rallumé. Réessayez plus tard.",
    },
    "ar": {
        "eyebrow": "مرشدك في رسائل الدوائر الألمانية",
        "tagline": "افهم كل رسالة من الدوائر الألمانية.",
        "lead": "التقط صورة للرسالة. يخبرك Amt-Lotse بلغتك ماذا تطلب الرسالة، وحتى متى، وكم المبلغ — ويقرؤها لك بصوت عالٍ.",
        "badges": ["الذكاء الاصطناعي على حاسوبك", "8 لغات", "يقرأ بصوت عالٍ", "اسأل بصوتك"],
        "how_h": "كيف يعمل",
        "how": [("صورة أو ملف", "صوّر الرسالة بهاتفك أو اختر ملف PDF."),
                ("جواب واضح", "ماذا عليك أن تفعل، والموعد، والمبلغ — مع إضافة إلى التقويم."),
                ("استمع واسأل", "استمع إليها مقروءة واطرح أسئلتك بصوتك.")],
        "feat_h": "صُنع لمن يحتاجه أكثر",
        "feats": [("lock", "خاص", "بلا ذكاء اصطناعي سحابي: تُقرأ الرسالة وتُشرح على هذا الحاسوب."),
                  ("check", "أرقام موثوقة", "يتم التحقق من المواعيد والمبالغ في الرسالة نفسها، ولا تُخترع أبدًا."),
                  ("eye", "سهل الاستخدام", "خط كبير، تباين عالٍ، ويعمل مع قارئ الشاشة."),
                  ("pen", "رد بالألمانية", "يكتب لك ردًا مهذبًا لتراجعه وترسله.")],
        "or_file": "أو اختر ملفًا (صورة، PDF، نص)",
        "drop": "اسحب الرسالة إلى هنا أو انقر للاختيار",
        "again": "🔄 اشرح مرة أخرى باللغة المختارة",
        "expl_h": "ماذا تعني الرسالة", "facts_h": "أهم المعلومات بنظرة واحدة",
        "examples": ["موعد", "تذكير بالدفع", "مصلحة الضرائب", "التأمين الصحي"],
        "badge_cloud": "ذكاء اصطناعي خاص، بلا شركات", "private_cloud": "بلا شركات ذكاء اصطناعي: يعمل الذكاء الاصطناعي على حاسوب خاص عبر اتصال مشفّر.",
        "open_app": 'افتح Amt-Lotse', "checking": 'جارٍ التحقق من تشغيل خادم الذكاء الاصطناعي …',
        "ai_on": "الذكاء الاصطناعي جاهز", "ai_off_h": "خادم الذكاء الاصطناعي متوقف",
        "ai_off": "الحاسوب الذي يشغّل الذكاء الاصطناعي مطفأ الآن. يمكن شرح الرسائل مرة أخرى عندما يُشغَّل. يرجى المحاولة لاحقًا.",
    },
    "tr": {
        "eyebrow": "Alman resmî yazışmalarında rehberiniz",
        "tagline": "Alman kurumlarından gelen her mektubu anlayın.",
        "lead": "Fotoğraf çekin. Amt-Lotse size kendi dilinizde mektubun ne istediğini, son tarihi ve tutarı söyler — ve sesli okur.",
        "badges": ["Yapay zekâ bilgisayarınızda", "8 dil", "Sesli okur", "Sesle sorun"],
        "how_h": "Nasıl çalışır",
        "how": [("Fotoğraf veya dosya", "Mektubu telefonunuzla çekin ya da bir PDF seçin."),
                ("Net bir cevap", "Ne yapmanız gerektiği, son tarih ve tutar — ayrıca bir takvim kaydı."),
                ("Dinleyin ve sorun", "Sesli dinleyin ve sorularınızı sesle sorun.")],
        "feat_h": "En çok ihtiyacı olanlar için yapıldı",
        "feats": [("lock", "Gizli", "Bulut yapay zekâsı yok: mektup bu bilgisayarda okunur ve açıklanır."),
                  ("check", "Güvenilir rakamlar", "Tarihler ve tutarlar mektupta kontrol edilir, asla uydurulmaz."),
                  ("eye", "Erişilebilir", "Büyük yazı, yüksek kontrast, ekran okuyucularla çalışır."),
                  ("pen", "Almanca cevap", "Kontrol edip göndermeniz için kibar bir cevap yazar.")],
        "or_file": "ya da bir dosya seçin (fotoğraf, PDF, metin)",
        "drop": "Mektubu buraya bırakın veya seçmek için tıklayın",
        "again": "🔄 Seçilen dilde yeniden açıkla",
        "expl_h": "Mektup ne anlama geliyor", "facts_h": "Bir bakışta önemli bilgiler",
        "examples": ["randevu", "ödeme hatırlatması", "vergi dairesi", "sağlık sigortası"],
        "badge_cloud": "Özel yapay zekâ, şirket yok", "private_cloud": "Yapay zekâ şirketi yok: yapay zekâ, şifreli bir bağlantıyla ulaşılan özel bir bilgisayarda çalışır.",
        "open_app": "Amt-Lotse'yi aç", "checking": 'Yapay zekâ sunucusunun açık olup olmadığı kontrol ediliyor …',
        "ai_on": "Yapay zekâ hazır", "ai_off_h": "Yapay zekâ sunucusu kapalı",
        "ai_off": "Yapay zekâyı çalıştıran bilgisayar şu anda kapalı. Açıldığında mektuplar yeniden açıklanabilir. Lütfen daha sonra tekrar deneyin.",
    },
    "uk": {
        "eyebrow": "Ваш провідник у німецьких офіційних листах",
        "tagline": "Розумійте кожен лист від німецьких установ.",
        "lead": "Сфотографуйте лист. Amt-Lotse пояснить вашою мовою, чого хоче лист, до якого числа і скільки — і прочитає вголос.",
        "badges": ["ШІ на вашому комп’ютері", "8 мов", "Читає вголос", "Питайте голосом"],
        "how_h": "Як це працює",
        "how": [("Фото або файл", "Сфотографуйте лист телефоном або виберіть PDF."),
                ("Зрозуміла відповідь", "Що робити, термін і сума — а ще запис у календар."),
                ("Слухайте й питайте", "Послухайте лист уголос і ставте запитання голосом.")],
        "feat_h": "Створено для тих, кому це найпотрібніше",
        "feats": [("lock", "Приватно", "Без хмарного ШІ: лист читається й пояснюється на цьому комп’ютері."),
                  ("check", "Цифри, яким можна вірити", "Терміни й суми перевіряються в листі й ніколи не вигадуються."),
                  ("eye", "Доступно", "Великий шрифт, висока контрастність, підтримка програм читання екрана."),
                  ("pen", "Відповідь німецькою", "Пише ввічливу відповідь, яку ви перевірите й надішлете.")],
        "or_file": "або виберіть файл (фото, PDF, текст)",
        "drop": "Перетягніть лист сюди або натисніть, щоб вибрати",
        "again": "🔄 Пояснити ще раз вибраною мовою",
        "expl_h": "Що означає лист", "facts_h": "Головне з першого погляду",
        "examples": ["зустріч", "нагадування про оплату", "податкова", "медичне страхування"],
        "badge_cloud": "Приватний ШІ, без ШІ-компаній", "private_cloud": "Жодної ШІ-компанії: ШІ працює на приватному комп’ютері через зашифроване з’єднання.",
        "open_app": 'Відкрити Amt-Lotse', "checking": 'Перевіряємо, чи увімкнений сервер ШІ …',
        "ai_on": "ШІ готовий", "ai_off_h": "Сервер ШІ вимкнено",
        "ai_off": "Комп’ютер, на якому працює ШІ, зараз вимкнений. Листи знову можна буде пояснити, щойно його увімкнуть. Спробуйте пізніше.",
    },
    "ru": {
        "eyebrow": "Ваш проводник в немецких официальных письмах",
        "tagline": "Понимайте каждое письмо от немецких ведомств.",
        "lead": "Сфотографируйте письмо. Amt-Lotse объяснит на вашем языке, чего хочет письмо, до какого числа и сколько — и прочитает вслух.",
        "badges": ["ИИ на вашем компьютере", "8 языков", "Читает вслух", "Спрашивайте голосом"],
        "how_h": "Как это работает",
        "how": [("Фото или файл", "Сфотографируйте письмо телефоном или выберите PDF."),
                ("Понятный ответ", "Что делать, срок и сумма — и запись в календарь."),
                ("Слушайте и спрашивайте", "Послушайте письмо вслух и задавайте вопросы голосом.")],
        "feat_h": "Сделано для тех, кому это нужнее всего",
        "feats": [("lock", "Приватно", "Без облачного ИИ: письмо читается и объясняется на этом компьютере."),
                  ("check", "Цифрам можно верить", "Сроки и суммы проверяются по письму и никогда не выдумываются."),
                  ("eye", "Доступно", "Крупный шрифт, высокий контраст, работает с экранными дикторами."),
                  ("pen", "Ответ на немецком", "Пишет вежливый ответ, который вы проверите и отправите.")],
        "or_file": "или выберите файл (фото, PDF, текст)",
        "drop": "Перетащите письмо сюда или нажмите, чтобы выбрать",
        "again": "🔄 Объяснить снова на выбранном языке",
        "expl_h": "Что означает письмо", "facts_h": "Главное с первого взгляда",
        "examples": ["встреча", "напоминание об оплате", "налоговая", "медицинская страховка"],
        "badge_cloud": "Частный ИИ, без ИИ-компаний", "private_cloud": "Никаких ИИ-компаний: ИИ работает на частном компьютере через зашифрованное соединение.",
        "open_app": 'Открыть Amt-Lotse', "checking": 'Проверяем, включён ли сервер ИИ …',
        "ai_on": "ИИ готов", "ai_off_h": "Сервер ИИ выключен",
        "ai_off": "Компьютер, на котором работает ИИ, сейчас выключен. Письма снова можно будет объяснить, как только его включат. Попробуйте позже.",
    },
    "fa": {
        "eyebrow": "راهنمای شما در نامه‌های اداری آلمان",
        "tagline": "هر نامه از اداره‌های آلمان را بفهمید.",
        "lead": "از نامه عکس بگیرید. Amt-Lotse به زبان شما می‌گوید نامه چه می‌خواهد، تا کی و چقدر — و آن را بلند می‌خواند.",
        "badges": ["هوش مصنوعی روی رایانهٔ شما", "۸ زبان", "بلند می‌خواند", "پرسش با صدا"],
        "how_h": "چطور کار می‌کند",
        "how": [("عکس یا فایل", "با گوشی از نامه عکس بگیرید یا یک PDF انتخاب کنید."),
                ("پاسخ روشن", "چه باید بکنید، مهلت و مبلغ — همراه با یادداشت در تقویم."),
                ("گوش دهید و بپرسید", "بشنوید که نامه بلند خوانده می‌شود و با صدا سؤال بپرسید.")],
        "feat_h": "ساخته‌شده برای کسانی که بیش از همه به آن نیاز دارند",
        "feats": [("lock", "خصوصی", "بدون هوش مصنوعی ابری: نامه روی همین رایانه خوانده و توضیح داده می‌شود."),
                  ("check", "عددهای قابل اعتماد", "مهلت‌ها و مبلغ‌ها با خود نامه بررسی می‌شوند و هرگز ساخته نمی‌شوند."),
                  ("eye", "دسترس‌پذیر", "متن بزرگ، کنتراست بالا، سازگار با صفحه‌خوان."),
                  ("pen", "پاسخ به آلمانی", "یک پاسخ مؤدبانه می‌نویسد تا شما بررسی و ارسال کنید.")],
        "or_file": "یا یک فایل انتخاب کنید (عکس، PDF، متن)",
        "drop": "نامه را اینجا رها کنید یا برای انتخاب کلیک کنید",
        "again": "🔄 دوباره به زبان انتخاب‌شده توضیح بده",
        "expl_h": "معنی نامه", "facts_h": "نکات اصلی در یک نگاه",
        "examples": ["وقت ملاقات", "یادآوری پرداخت", "اداره مالیات", "بیمه درمانی"],
        "badge_cloud": "هوش مصنوعی خصوصی، بدون شرکت", "private_cloud": "بدون شرکت هوش مصنوعی: هوش مصنوعی روی یک رایانهٔ خصوصی و از راه یک اتصال رمزگذاری‌شده اجرا می‌شود.",
        "open_app": 'باز کردن Amt-Lotse', "checking": 'در حال بررسی روشن بودن سرور هوش مصنوعی …',
        "ai_on": "هوش مصنوعی آماده است", "ai_off_h": "سرور هوش مصنوعی خاموش است",
        "ai_off": "رایانه‌ای که هوش مصنوعی روی آن اجرا می‌شود اکنون خاموش است. به‌محض روشن شدن، نامه‌ها دوباره توضیح داده می‌شوند. لطفاً بعداً دوباره امتحان کنید.",
    },
    "de": {
        "eyebrow": "Ihr Lotse durch Briefe vom Amt",
        "tagline": "Briefe vom Amt einfach verstehen.",
        "lead": "Machen Sie ein Foto. Amt-Lotse sagt Ihnen in einfacher Sprache: Was will der Brief? Bis wann? Wie viel? Und liest es vor.",
        "badges": ["KI auf Ihrem Computer", "8 Sprachen", "Liest vor", "Fragen mit der Stimme"],
        "how_h": "So geht es",
        "how": [("Foto oder Datei", "Fotografieren Sie den Brief mit dem Handy oder wählen Sie ein PDF."),
                ("Klare Antwort", "Was Sie tun müssen, die Frist und der Betrag – dazu ein Kalender-Eintrag."),
                ("Hören und fragen", "Hören Sie den Brief vorgelesen und stellen Sie Fragen mit der Stimme.")],
        "feat_h": "Gemacht für Menschen, die es am meisten brauchen",
        "feats": [("lock", "Privat", "Keine Cloud-KI: Der Brief wird auf diesem Computer gelesen und erklärt."),
                  ("check", "Zahlen, auf die Sie sich verlassen können", "Fristen und Beträge werden im Brief geprüft, nie erfunden."),
                  ("eye", "Barrierearm", "Große Schrift, hoher Kontrast, für Bildschirmleser."),
                  ("pen", "Antwort auf Deutsch", "Schreibt eine höfliche Antwort. Sie prüfen und schicken sie.")],
        "or_file": "oder eine Datei wählen (Foto, PDF, Text)",
        "drop": "Brief hierher ziehen oder klicken zum Auswählen",
        "again": "🔄 Noch einmal in der gewählten Sprache erklären",
        "expl_h": "Was der Brief bedeutet", "facts_h": "Das Wichtigste auf einen Blick",
        "examples": ["Termin", "Zahlungserinnerung", "Steuern", "Krankenversicherung"],
        "badge_cloud": "Private KI, keine KI-Firma", "private_cloud": "Keine KI-Firma: Die KI läuft auf einem privaten Computer, erreichbar über eine verschlüsselte Verbindung.",
        "open_app": 'Amt-Lotse öffnen', "checking": 'Prüfe, ob der KI-Server an ist …',
        "ai_on": "KI bereit", "ai_off_h": "Der KI-Server ist aus",
        "ai_off": "Der Computer mit der KI ist gerade ausgeschaltet. Sobald er wieder an ist, können Briefe erklärt werden. Bitte versuchen Sie es später noch einmal.",
    },
}


def _dir(lang: str) -> str:
    return "rtl" if lang in RTL_LANGUAGES else "ltr"


def brand_html() -> str:
    return f'<div class="brand">{LOGO}<span>Amt-Lotse</span></div>'


def hero_html(lang: str, cloud: bool = False) -> str:
    """cloud: the app runs online and the AI on a private PC, so "AI on this computer" would not be true."""
    t = TEXT[lang]
    badges = [t["badge_cloud"], *t["badges"][1:]] if cloud else t["badges"]
    badges = "".join(f"<li>{escape(b)}</li>" for b in badges)
    return (f'<section class="hero" dir="{_dir(lang)}" lang="{lang}"><p class="eyebrow">{escape(t["eyebrow"])}</p>'
            f'<h1>{escape(t["tagline"])}</h1><p class="lead">{escape(t["lead"])}</p>'
            f'<ul class="badges">{badges}</ul></section>')


def art_html() -> str:
    return f'<div class="hero-art">{HERO_ART}</div>'


def info_html(lang: str, cloud: bool = False) -> str:
    """'How it works' and the feature cards, below the tool."""
    t = TEXT[lang]
    feats = [(k, h, t["private_cloud"] if cloud and k == "lock" else p) for k, h, p in t["feats"]]
    steps = "".join(f'<li><span class="num">{i}</span><h3>{escape(h)}</h3><p>{escape(p)}</p></li>'
                    for i, (h, p) in enumerate(t["how"], 1))
    feats = "".join(f'<li><span class="ico" aria-hidden="true">{ICONS[k]}</span><h3>{escape(h)}</h3><p>{escape(p)}</p></li>'
                    for k, h, p in feats)
    return (f'<section class="info" dir="{_dir(lang)}" lang="{lang}"><h2>{escape(t["how_h"])}</h2>'
            f'<ol class="steps">{steps}</ol><h2>{escape(t["feat_h"])}</h2><ul class="feats">{feats}</ul></section>')


def example_labels(lang: str) -> list[str]:
    return [f"📄 {office} · {hint}" for office, hint in zip(EXAMPLE_OFFICES, TEXT[lang]["examples"], strict=True)]


def facts_html(a: Analysis, lang: str, warning: str = "") -> str:
    """The checked facts as tiles with icons: sender, deadline, money, reference number."""
    t = CARD[lang]
    tiles = [("🏢", t["from"], escape(a.info.sender or "—"), "")]

    if a.deadline:
        days = (a.deadline - date.today()).days
        when = t["today"] if days == 0 else (t["overdue"].format(n=-days) if days < 0 else t["days"].format(n=days))
        tiles.append(("⏰", t["deadline"], f'{escape(say_date(a.deadline, lang))}<small>{escape(when)}</small>',
                      " hot" if days <= 7 else ""))
    else:
        tiles.append(("⏰", t["deadline"], escape(t["none"]), " calm"))

    if a.amount is not None:
        tiles.append(("💶", t["pay"], f'<span class="money">{escape(_euro(a.amount))}</span>', ""))
    elif a.amount_unclear:
        tiles.append(("💶", t["pay"], escape(t["unclear"]), " hot"))
    elif a.receives is not None:
        tiles.append(("💶", t["get"], f'<span class="money">{escape(_euro(a.receives))}</span>', " good"))
    else:
        tiles.append(("💶", t["pay"], escape(t["nothing"]), " good"))

    if a.reference:
        tiles.append(("🔖", t["ref"], f'<span class="ref">{escape(a.reference)}</span><small>{escape(t["ref_hint"])}</small>', ""))

    body = "".join(f'<li class="fact{css}"><span class="ico" aria-hidden="true">{icon}</span>'
                   f'<span class="label">{escape(label)}</span><span class="value" dir="auto">{value}</span></li>'
                   for icon, label, value, css in tiles)
    warn = f'<p class="warn" role="note">⚠️ {escape(warning)}</p>' if warning else ""
    title = escape(TEXT[lang]["facts_h"])
    return f'<section class="facts" dir="{_dir(lang)}" aria-label="{title}">{warn}<ul>{body}</ul></section>'


def ai_status_html(lang: str, online: bool) -> str:
    """Always-online version only: a small green 'AI ready', or a clear notice that the AI computer is off."""
    t = TEXT[lang]
    if online:
        return f'<p class="ai-on" dir="{_dir(lang)}" role="status">{escape(t["ai_on"])}</p>'
    return (f'<div class="ai-off" dir="{_dir(lang)}" role="alert"><strong>{escape(t["ai_off_h"])}</strong>'
            f'<span>{escape(t["ai_off"])}</span></div>')
