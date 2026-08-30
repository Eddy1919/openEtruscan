#!/usr/bin/env python3
"""Batch 2 seeder — lexicon-tier gloss pairs collected from page-verifiable
online sources (2026-08-30 research pass). Appends to gold_glosses.jsonl,
skipping any etr form already present.

Every row below was found verbatim (or in trivially normalized
transliteration) on at least one of the SOURCES pages by a web-research
agent; nothing is reconstructed. Status is llm_checked (page-corroborated),
which per README is still below human verification. Disputes are recorded,
not resolved: where the standard references disagree (notably Steinbauer's
numeral row against the Bonfante/mainstream one), the row says so and
confidence is capped.

Run: python seed_lexicon_batch.py  (idempotent: skips existing etr forms)
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

HERE = Path(__file__).parent
TARGET = HERE / "gold_glosses.jsonl"
DATE = "2026-08-30"
BY = "Claude research agent, page-corroborated against the listed sources"

SOURCES = {
    "W": ("Bonfante & Bonfante 2002 glossary (via Wiktionary Appendix:Etruscan word list)",
          "https://en.wiktionary.org/wiki/Appendix:Etruscan_word_list"),
    "S": ("Steinbauer, Etruscan Vocabulary (etruskisch.de, companion to Neues Handbuch des Etruskischen 1999)",
          "http://www.etruskisch.de/pgs/vc.htm"),
    "M": ("Mc Callister & Mc Callister-Castillo 1999, Etruscan Glossary (per-entry Pallottino/Bonfante codes)",
          "https://www.almendron.com/blog/wp-content/images/2005/11/etruscan-glossary-callisters.pdf"),
    "LL": ("Liber Linteus glosses after van der Meer 2007 (Wikipedia: Liber Linteus)",
           "https://en.wikipedia.org/wiki/Liber_Linteus"),
    "N": ("Wikipedia: Etruscan numerals (incl. Tuscania dice; 2011 dice-statistics study)",
          "https://en.wikipedia.org/wiki/Etruscan_numerals"),
    "P": ("Wikipedia: Pyrgi Tablets", "https://en.wikipedia.org/wiki/Pyrgi_Tablets"),
    "D": ("German Wikipedia: Etruskische Sprache (secured-vocabulary table)",
          "https://de.wikipedia.org/wiki/Etruskische_Sprache"),
    "E": ("Wikipedia: Etruscan language", "https://en.wikipedia.org/wiki/Etruscan_language"),
    "B": ("fixed by a Latin-Etruscan bilingual (see bilinguals.jsonl; van Heems corpus PDF)",
          "https://lettres.sorbonne-universite.fr/sites/default/files/media/2020-05/coexistence_g-_van_heems_relu2.pdf"),
}

# (etr, gloss_en, lat, confidence, source_keys, notes)
ROWS = [
    # kinship, persons, pronouns
    ("apa", "father", "pater", "high", "WSD", ""),
    ("ati", "mother", "mater", "high", "WSD", ""),
    ("ati nacna", "grandmother", "avia", "high", "WSM", "also nacnuva"),
    ("apa nacna", "grandfather", "avus", "medium", "SM", ""),
    ("clan", "son", "filius", "high", "WSDEB", "fixed by bilingual ET Ar 1.8 (v. cazi c. clan = C. Cassius C. f.); pl. clenar"),
    ("sec", "daughter", "filia", "high", "WSD", "also seχ"),
    ("puia", "wife", "uxor", "high", "WSDM", ""),
    ("ruva", "brother", "frater", "high", "WDM", ""),
    ("papa", "grandfather", "avus", "high", "WSDM", ""),
    ("teta", "grandmother", "avia", "high", "WSDM", ""),
    ("papals", "grandchild through the grandfather", "nepos", "high", "WSM", "also papacs"),
    ("tetals", "grandchild through the grandmother", "nepos", "high", "SM", ""),
    ("neftś", "nephew, grandson", "nepos", "high", "WS", "also nefts"),
    ("prumaθś", "great-grandson or grand-nephew", "pronepos", "high", "WS", "relation one generation beyond nepos; exact line debated"),
    ("husiur", "children, youths", "liberi", "high", "WSM", "stem hus-"),
    ("clanti", "adoptive son", "filius adoptivus", "high", "WS", ""),
    ("ativu", "dear mother or stepmother", None, "low", "WS", "glosses diverge between W and S"),
    ("lautn", "family, household, gens", "familia", "high", "WM", "S dissents ('possession'); also lautun"),
    ("lautni", "freedman", "libertus", "high", "WSMB", "fixed twice by bilinguals (ET Pe 1.211 = TLE 606; ET Cl 1.219)"),
    ("lautniθa", "freedwoman", "liberta", "high", "WSM", "also lautnita"),
    ("etera", "dependent person: foreigner, client or slave", None, "low", "WSM", "exact social status contested"),
    ("snenaθ", "maid, female companion", "ancilla", "high", "WSM", ""),
    ("tusurθir", "married couple(s)", "coniuges", "medium", "W", ""),
    ("pava", "boy, youth", "puer", "medium", "W", ""),
    ("talitha", "girl", "puella", "low", "W", "isolated; anomalous form"),
    ("aθumic", "noble, nobility", "nobilis", "high", "WM", "stem aθumi-"),
    ("afer", "ancestors or descendants", "maiores", "low", "W", "direction of the relation unclear (afr/aterś)"),
    ("an", "he, she; relative pronoun", "is", "medium", "W", ""),
    ("un", "you (dative)", "tibi", "medium", "WM", "S dissents: 'a pouring-out (libation)'"),
    ("ca", "this (demonstrative)", "hic", "high", "WSM", "stem family ca/eca/cn/itun; second stem ta/eta/tn"),
    ("cla", "of this", "huius", "medium", "SW", "genitive of ca; also clal/cal"),
    ("ipa", "who, which", "qui", "high", "WM", ""),
    ("ipe ipa", "whoever, whatever", "quicumque", "medium", "W", ""),
    ("sa-", "self", "ipse", "high", "WS", ""),
    ("hel", "own, proper", "suus", "medium", "W", "also hels"),
    ("cehen", "this one here", "hic", "low", "WS", "S dissents: 'outer, outside'"),
    # society, offices, law
    ("zilaθ", "chief magistrate", "praetor", "high", "WSMP", "also zilc/zil; Pallottino TLE glosses 'praetor'"),
    ("zilaθ meχl rasnal", "magistrate of the etruscan league", "praetor etruriae", "medium", "M", ""),
    ("zilaχnuce", "held the chief magistracy", "praetor fuit", "medium", "M", "also zilaχnce"),
    ("purθ", "a magistracy (dictator-like?)", None, "high", "WM", "title certain, function not; also purθne/eprθne"),
    ("camθi", "a magistracy", None, "high", "WM", "title certain, function not"),
    ("maru", "civic-religious office (maro)", None, "high", "SME", "cf. Umbrian maron-; marunuχ on the Churcles sarcophagus"),
    ("macstrev", "a magistracy", None, "high", "WM", "cf. Latin magister?"),
    ("cechase", "magistracy or priesthood", None, "high", "WM", "cecha- derivatives"),
    ("tamera", "a magistracy or burial chamber", None, "low", "WSM", "two competing meanings in the literature"),
    ("parniχ", "office or priesthood", None, "medium", "W", ""),
    ("ten-", "to hold (an office)", "gerere", "medium", "W", "participle tenu"),
    ("lauχume", "king", "lucumo", "high", "W", "the Etruscan form behind the Latin authors' lucumo gloss; also lauχum"),
    ("lucairce", "to rule, act as lucumo", "regnare", "medium", "W", ""),
    ("meχ", "people, league", "populus", "medium", "WM", "S dissents 'lady, queen'; meχ θuta ~ res publica (M)"),
    ("meθlum", "district, nation, territory", None, "high", "WSM", ""),
    ("spur-", "city, community", "urbs", "high", "WSM", "also spura"),
    ("spurana", "civic, of the city", "publicus", "high", "WM", "also spureni"),
    ("rasna", "the etruscan people, public", None, "high", "WSEM", "cf. Dionysius of Halicarnassus, Rasenna; also raśna"),
    ("tuθi", "community, state", "civitas", "medium", "WS", "S dissents 'vow, votum'; also tuti"),
    ("tuθina", "public, of the community", "publicus", "medium", "WS", "S dissents 'votive gift'"),
    ("rumaχ", "roman", "romanus", "high", "WM", ""),
    ("creice", "greek", "graecus", "high", "WM", "also kraikalu-"),
    ("naper", "measure of land area", None, "high", "WM", "S dissents 'border stones'"),
    ("tezan", "boundary-marker or road", None, "low", "S", "contested"),
    ("cilθ", "citadel, sanctuary or people", "arx", "low", "WMLL", "three-way dispute"),
    ("tevaraθ", "umpire, judge at the games", "arbiter", "high", "WSM", ""),
    ("zeri", "rite, legal action", None, "medium", "WS", "S dissents 'free, unclouded'"),
    ("tupi", "punishment, penalty", "poena", "medium", "S", ""),
    ("cecha", "rite, ceremony, sacred law", "ritus", "medium", "WMS", "S dissents 'treaty'; Cristofani 'above'"),
    ("ratum", "according to rite or law", "rite", "high", "WM", ""),
    ("-θuras", "member(s) of the group or family of (suffix)", None, "medium", "W", ""),
    ("paχaθur", "bacchic sodality, maenads", "bacchae", "high", "WM", "maru paχathuras = priest of Bacchus (Pallottino)"),
    ("huzrnatre", "college of youths", "iuventus", "medium", "W", ""),
    ("lautneteri", "freedman-client class", None, "medium", "M", ""),
    ("macstrna", "mastarna (figure from magister)", "mastarna", "medium", "WS", "Servius Tullius per Claudius' Lyon speech"),
    # religion, ritual, dedication
    ("ais", "god", "deus", "high", "WSEM", "also eis; cf. the aesar/aisoi ancient glosses"),
    ("aiser", "gods", "dei", "high", "EMW", "also eisar/eiser"),
    ("aisna", "divine; divine rite", "sacrum", "high", "WSLL", "also eisna"),
    ("flere", "deity, numen", "numen", "high", "WSLL", ""),
    ("fler", "offering, sacrifice", "hostia", "high", "WSLL", ""),
    ("flerχva", "offerings (collective)", None, "high", "WLL", ""),
    ("farθan", "genius; to beget", "genius", "high", "WMLL", ""),
    ("cepen", "priest", "sacerdos", "high", "WLLM", "specialized: θaurχ 'of the tomb', tutin 'of the village'; S dissents 'under, below'"),
    ("celu", "a priestly title", None, "medium", "W", ""),
    ("netśvis", "haruspex", "haruspex", "high", "WSMB", "fixed by the Pesaro bilingual (TLE 697); also ET Cl 1.1036"),
    ("trutnvt", "diviner-priest, examiner of omens", "fulguriator", "high", "WSB", "Pesaro bilingual; exact force debated; also trutnuθ"),
    ("frontac", "lightning-interpreter", "fulguriator", "high", "WB", "Pesaro bilingual"),
    ("neθśrac", "haruspicy", "haruspicina", "high", "W", "zich neθśrac 'book on haruspicy', Pulenas sarcophagus"),
    ("sacni", "consecrated, holy", "sacer", "medium", "WM", "S dissents 'citizen'; M (gm97) 'sanctuary'"),
    ("śacnicś", "sacred fraternity or priesthood", None, "medium", "LLM", "sacnicleri 'for the sanctuary'"),
    ("tmia", "temple, sacred building", "templum", "high", "WSP", "Pyrgi tablets"),
    ("heramaśva", "statues or sacred buildings", None, "medium", "WP", "Pyrgi; gloss debated"),
    ("cver", "gift, votive object", "donum", "high", "WSM", "also cvera"),
    ("cana", "image, work of art", None, "high", "WSM", "also kana"),
    ("alpan", "gift, offering; gladly", "libens", "high", "WSM", "also alpnu"),
    ("turza", "offering", None, "high", "WM", ""),
    ("tinścvil", "offering to tin, consecrated object", "donum", "high", "WS", "cvil 'gift'"),
    ("cletram", "litter or basin for offerings", None, "high", "WSLL", ""),
    ("vacl", "libation, votive act", "libatio", "high", "WLL", "also vacal/vacil"),
    ("zusleva", "sacrificial victims, piglets", None, "high", "WLLM", "singular zusle"),
    ("faśe", "offered substance (mash, bread or oil)", None, "high", "WSLL", "exact referent open; also faśei/faś"),
    ("sul", "liquid used in sacrifice", None, "medium", "W", ""),
    ("alphaze", "an offering (barley-meal?)", "mola", "medium", "W", ""),
    ("aper", "funerary rite or sacrifice", None, "high", "WM", "stem apir-"),
    ("nunθen", "to offer with invocation, invoke", "invocare", "high", "WLL", "also nunθena"),
    ("θez-", "to sacrifice, present an offering", "immolare", "high", "WLL", ""),
    ("trin-", "to plead, supplicate, utter", "supplicare", "high", "WM", ""),
    ("ilucu", "offering or festival term; calendar period", None, "low", "WS", "two readings (W offering/festival; S calendar period)"),
    ("mulu", "gave, dedicated (ex-voto)", "donavit", "high", "WSEM", "muluvanice/mulvanice"),
    ("tur-", "to give", "dare", "high", "WSEPM", "turce/turuce 'gave'"),
    ("al-", "to give, offer", "dare", "high", "WS", "alice 'gave'"),
    ("acas", "made, offered", "fecit", "medium", "W", "acasce; stem ac-"),
    ("zinace", "made, fashioned (craftsman formula)", "fecit", "high", "WS", "also zinaku"),
    ("cerichunce", "erected, built", "aedificavit", "high", "WS", "ce(ri)nu 'was built'"),
    ("θam-", "to build, found", "condere", "high", "WP", "also them-"),
    ("hec-", "to put, place", "ponere", "high", "WS", "also heci"),
    ("śuθ-", "to place, set, deposit", "ponere", "high", "WS", "also sut-, śatena/sath- 'establish'"),
    ("zich", "writing, book, inscription", "scriptum", "high", "WS", "also zic"),
    ("zichuche", "was written, incised", "scriptum est", "high", "WS", ""),
    ("zichu", "writer, scribe", "scriba", "high", "WSB", "bilingual ET Cl 1.320: vl. zicu = Q. SCRIBONIVS (translated gentilicium)"),
    ("urθanike", "made, caused to be", "fecit", "medium", "W", "stem urθan-"),
    ("ut-", "to carry out, perform, give", None, "medium", "W", ""),
    ("us-", "to draw (water), ladle", "haurire", "medium", "W", "useti"),
    ("am-", "to be", "esse", "high", "WSP", "ame/amce 'was'"),
    ("acnanas", "having borne, begotten (children)", "genuit", "high", "SP", "also acna(s)"),
    ("arce", "raised (a child)", "educavit", "medium", "S", ""),
    ("raχθ", "on the fire (offering placement)", "in igne", "medium", "LL", ""),
    ("luθ", "stone, altar-stone", "lapis", "high", "WLL", "luθti 'on the stone'"),
    ("tesinθ", "caretaker", "curator", "high", "WM", ""),
    ("teras", "prodigy, portent", "prodigium", "medium", "W", "cf. Greek teras"),
    # death and the tomb
    ("leine", "died", "obiit", "medium", "WM", "S dissents 'at the age of'"),
    ("sval-", "to live", "vivere", "high", "WSM", "svalce 'lived', svalθas"),
    ("ziva-", "the dead, deceased (or: having lived)", "mortuus", "low", "WMS", "live dispute: 'dead' vs 'alive'; S 'kin'"),
    ("śuθina", "for the tomb (grave-gift marker)", "sepulcralis", "high", "WSM", "scratched on mirrors and grave goods"),
    ("hinθial", "soul, shade, ghost", "umbra", "high", "WSM", ""),
    ("hinθ", "below, infernal", "infernus", "medium", "W", "also hinθi(a)"),
    ("man", "the dead", "manes", "medium", "WS", "S dissents 'tombstone'; also mani"),
    ("mun-", "underground chamber, tomb", "hypogeum", "medium", "W", "also muni"),
    ("murś", "urn, sarcophagus", "urna", "high", "SM", ""),
    ("capra", "urn, ash-container, coffin", "urna", "high", "WS", ""),
    ("mutna", "sarcophagus, coffin", None, "medium", "S", ""),
    ("tus", "funerary niche, resting-place", "loculus", "high", "WS", ""),
    ("zelar", "burial niches", "loculi", "medium", "S", ""),
    ("hupnina", "funeral couch, kline-coffin", None, "medium", "S", ""),
    ("penθna", "cippus, inscribed stone", "cippus", "high", "WS", "also penθuna"),
    ("θaure", "tomb; funerary", "sepulcrum", "high", "WLLM", "θaurχ 'funerary'; S dissents 'property?'"),
    ("ces-", "to lie (buried), be laid", "situs est", "high", "WS", "cesu"),
    ("tesham-", "burial; to care for (the dead)", None, "medium", "SW", "stem tes-"),
    ("nesna", "belonging to the dead", None, "high", "WM", ""),
    ("sanisva", "bones (of the deceased)", "ossa", "medium", "W", "M (am91) dissents 'blessed?'"),
    ("san-", "deceased, ancestor-", None, "medium", "W", ""),
    ("favi", "grave vault", None, "medium", "W", "cf. Latin favissae?"),
    # time and calendar
    ("avil", "year", "annus", "high", "WSDEPM", ""),
    ("avilχval", "yearly, of the years", "annuus", "high", "MP", ""),
    ("tiur", "moon; month", "mensis", "high", "WSDP", "also tiu/tivr"),
    ("tin-", "day", "dies", "high", "WSLL", "also the god Tin/Tinia = Jupiter"),
    ("θesan", "dawn, morning", "aurora", "high", "WSLLM", "also the dawn-goddess"),
    ("usil", "sun", "sol", "high", "WSD", "S adds noon/south"),
    ("uslane", "at noon", "meridie", "medium", "WS", ""),
    ("cla θesan", "on the morrow, in the morning", "mane", "medium", "LL", ""),
    ("θui", "here, now", "hic", "high", "WM", "S dissents 'inside'"),
    ("θuni", "at first", "primum", "medium", "W", ""),
    ("masan", "a month name (december? placement debated)", None, "low", "W", "also masn"),
    ("θucte", "a month name (july/august?)", None, "low", "WS", "placement contested"),
    ("acale", "june (attested etruscan form)", "iunius", "high", "WS", "native form behind the Liber glossarum aclus"),
    ("apirase", "in april (locative)", "aprilis", "high", "WSM", "native form behind cabreas/capre (Tabula Capuana)"),
    # numerals beyond the dice six
    ("semφ", "seven (uncertain)", "septem", "medium", "WDN", ""),
    ("cezp", "eight (hypothesized)", "octo", "medium", "WDN", ""),
    ("nurφ", "nine (single attestation)", "novem", "medium", "WDN", ""),
    ("śar", "ten", "decem", "high", "WDN", "minority duodecimal view: 12, with halχ = 10; also zar"),
    ("zaθrum", "twenty", "viginti", "high", "WSDN", ""),
    ("ciem zaθrum", "seventeen (three from twenty, subtractive)", None, "high", "SN", ""),
    ("eslem zaθrum", "eighteen (two from twenty)", "duodeviginti", "high", "SN", ""),
    ("θunem zaθrum", "nineteen (one from twenty)", "undeviginti", "high", "SN", ""),
    ("cialχ", "thirty", "triginta", "high", "WSN", "also cealχ"),
    ("muvalχ", "fifty", "quinquaginta", "medium", "WS", "S 'forty', tied to his maχ=4 row"),
    ("śealχ", "sixty or forty", None, "low", "WS", "tied to the śa dispute"),
    ("semφalχ", "seventy (uncertain)", "septuaginta", "medium", "W", ""),
    ("cezpalχ", "eighty (uncertain)", "octoginta", "medium", "W", ""),
    ("huθzars", "sixteen (if huθ=6)", "sedecim", "low", "S", "S reads fifteen; tied to the numeral dispute"),
    ("θunz", "once", "semel", "high", "WS", ""),
    ("eslz", "twice", "bis", "medium", "S", ""),
    ("ciz", "three times", "ter", "high", "WSLL", ""),
    ("huθz", "six times", "sexies", "medium", "W", "also cezpz 'eight times', nurφzi 'nine times'"),
    ("θunur", "one at a time", "singuli", "medium", "W", ""),
    ("θunśna", "first", "primus", "medium", "W", "also θunina"),
    ("sarsnach", "tenth", "decimus", "medium", "W", "sarsnau 'group of ten'"),
    ("χimθ", "one hundred (weakly established)", "centum", "low", "N", ""),
    # vessels, objects, materials
    ("aska", "askos, oil-flask", None, "high", "WSM", "Greek loan; aska eleivana 'of oil'"),
    ("qutun", "jug, pitcher", None, "high", "WSEM", "Greek kothon loan; also qutum"),
    ("qutumuza", "little jug", None, "medium", "S", ""),
    ("culichna", "kylix-type cup", "culigna", "high", "WSM", "Greek kylix diminutive; also culχna"),
    ("lechtum", "lekythos", None, "high", "WSM", "Greek lekythos loan; lechtumuza 'small lekythos'"),
    ("pruchum", "jug (oinochoe-type)", None, "high", "WS", "Greek prochous loan; also pruχ"),
    ("θina", "ewer, water-jar, krater", None, "high", "WS", ""),
    ("θafna", "offering-cup, chalice", "patera", "high", "WSM", "also θapna"),
    ("spanti", "plate, shallow bowl", None, "high", "WSM", ""),
    ("cape", "vessel, container", "capis", "high", "WM", "also capi"),
    ("cupe", "cup", "cupa", "high", "WM", "loan-relation with Latin cupa"),
    ("patna", "a vessel type", "patina", "high", "WM", ""),
    ("larnas", "a vase type", None, "medium", "W", "Greek larnax?"),
    ("ulpaia", "wine-jar (olpe)", None, "medium", "W", "Greek olpe"),
    ("zavena", "two-handled cup (kantharos)", None, "medium", "S", "zavenuza diminutive; S cites Wallace, Studi Etruschi 64"),
    ("fasena", "libation vessel", None, "medium", "S", ""),
    ("vertun", "a vessel type", None, "low", "S", ""),
    ("huślna", "wine-mug or amphora (cultic)", None, "low", "S", ""),
    ("achapri", "jug, oinochoe", None, "medium", "S", ""),
    ("sunθeruza", "little round box", "pyxis", "high", "WS", ""),
    ("malena", "mirror", "speculum", "high", "WSELL", "also malstria"),
    ("sren", "figure, ornament", None, "high", "WMLL", "srencve 'decorated with figures'; S dissents 'upper'"),
    ("caper", "ritual cloak", None, "medium", "S", ""),
    ("tul", "stone", "lapis", "medium", "W", ""),
    ("zamaθi", "gold, golden object (or brooch)", "aurum", "medium", "WS", "referent debated; also zamθi"),
    ("vinum", "wine", "vinum", "high", "WSLLM", "loan; also vinm"),
    ("eleiva", "oil", "oleum", "high", "WS", "Greek elaiwon loan"),
    ("maθ", "honeyed drink, mead", "mulsum", "high", "WM", ""),
    ("θra", "milk? drank?", None, "low", "W", ""),
    ("vina", "vineyard", "vinea", "medium", "W", ""),
    ("athre", "building, hall", "atrium", "high", "WM", "loan-relation with Latin atrium"),
    ("cela", "room, chamber", "cella", "medium", "W", "loan-relation with Latin cella"),
    ("pera", "house", "domus", "medium", "S", "also per"),
    ("scuna", "place, room", None, "medium", "S", ""),
    ("culseva", "doors, gates", "ianuae", "medium", "W", ""),
    ("trepu", "craftsman, carpenter", "faber", "medium", "SB", "appellative behind gens Trepu/Trebonius (bilingual ET Cl 1.354)"),
    ("acil", "work, thing made; it is necessary", "opus", "medium", "W", ""),
    # nature, animals, body, space, particles
    ("cel", "earth, ground, land", "terra", "high", "WSLL", "cel-i 'on the ground'; also the earth-goddess Cel"),
    ("θi", "water", "aqua", "high", "WS", ""),
    ("una", "stream, flowing water", None, "medium", "S", ""),
    ("huin-", "spring, well", "fons", "medium", "S", ""),
    ("tisś", "lake", "lacus", "medium", "E", "Tabula Cortonensis"),
    ("pulumχva", "stars", "stellae", "high", "WSP", ""),
    ("falatu", "sky (attested form)", "caelum", "medium", "W", "native counterpart of the falado ancient gloss"),
    ("θevru", "bull", "taurus", "high", "WSM", "θevrumineś = Minotaur"),
    ("leu", "lion", "leo", "high", "WS", "loan"),
    ("tusna", "swan", "cygnus", "high", "SM", "Turan's swan"),
    ("hiuls", "owl", None, "high", "SM", ""),
    ("capu", "falcon (attested form)", "falco", "medium", "W", "native counterpart of the capys ancient gloss"),
    ("cal", "dog", "canis", "low", "W", "isolated"),
    ("hamφe-", "right(-hand)", "dexter", "high", "WSLL", "also namphe"),
    ("laive", "left", "laevus", "high", "WSLL", "also laiva-"),
    ("calθi", "here, in this place", "hic", "high", "WS", "also celθi/clθi/eclθi"),
    ("θar", "there", "ibi", "high", "WM", ""),
    ("epi", "in, to, up to, until", "usque ad", "medium", "W", "also pi/pul"),
    ("mur-", "to stay, dwell", "morari", "medium", "W", ""),
    ("itu-", "to divide", "dividere", "medium", "W", "cf. the ancient gloss itus ~ idus"),
    ("mean", "youth, childhood", "iuventus", "low", "S", ""),
    ("mlaχ", "good, beautiful", "bonus", "high", "WSM", "dedication formula mlaχ mlakas"),
    ("eθ", "thus, in this way", "ita", "medium", "W", "also et"),
    ("etnam", "and, also, again", "item", "high", "WM", ""),
    ("-c", "and (enclitic)", "-que", "high", "WLL", ""),
    ("nac", "when, as, after", "cum", "high", "PM", ""),
    ("ic", "as, like", "sicut", "high", "WM", "also iχ/iχnac"),
    ("enac", "then, afterwards", "deinde", "high", "WM", "also enaχ"),
    ("sve", "likewise", "item", "high", "WM", ""),
    ("heva", "all?", "omnes", "low", "S", ""),
    ("snuiaφ", "as much, as many as", "quot", "medium", "S", ""),
    ("hath", "to be favorable", "favere", "low", "W", ""),
    ("suplu", "flute-player (attested form)", "subulo", "high", "WM", "native counterpart of Varro's subulo gloss"),
    ("triumpe", "triumph (cry, procession)", "triumpus", "high", "WE", ""),
]


def parse_keys(keys: str) -> list[str]:
    """'WSLL' -> ['W', 'S', 'LL'] (LL is the only two-char key)."""
    out, i = [], 0
    while i < len(keys):
        if keys[i : i + 2] == "LL":
            out.append("LL")
            i += 2
        else:
            out.append(keys[i])
            i += 1
    return out


def main() -> None:
    existing = set()
    for line in TARGET.read_text().splitlines():
        if line.strip():
            existing.add(json.loads(line)["etr"])

    added, skipped = 0, 0
    with TARGET.open("a") as f:
        for etr, gloss, lat, conf, keys, note in ROWS:
            etr_n = unicodedata.normalize("NFC", etr).lower().strip()
            if etr_n in existing:
                skipped += 1
                continue
            key_list = parse_keys(keys)
            names = "; ".join(SOURCES[k][0] for k in key_list)
            rec = {
                "etr": etr_n,
                "gloss_en": gloss.lower(),
                "lat": lat,
                "source_type": "lexicon",
                "citation_primary": "inscriptional attestation; see the listed modern sources",
                "citation_modern": names,
                "confidence": conf,
                "notes": note,
                "adjudication": {"status": "llm_checked", "by": BY, "date": DATE},
                "check_url": SOURCES[key_list[0]][1],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            existing.add(etr_n)
            added += 1
    print(f"added {added}, skipped {skipped} already present, total rows {len(ROWS)}")


if __name__ == "__main__":
    main()
