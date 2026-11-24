# AI Heritage Short — Creative Design Specification

## 1. Narrative Concept: "ጣዕመ ትውፊት" (Taste of Heritage)

The short film is conceived as an intimate, reverent visual poem exploring the Ethiopian coffee ceremony (*Buna*) not merely as a beverage ritual, but as an ancient medium for generational storytelling, spiritual grounding, and community cohesion.

Through ten carefully structured shots spanning 75 seconds, grandmother **Emaye Ayelech** guides the viewer through each step of the ceremony, illuminating the philosophical parallel between the transformation of coffee beans and the enduring resilience of cultural heritage.

---

## 2. Character Profile: Emaye Ayelech

> [!NOTE]
> Emaye Ayelech is a completely fictional AI character developed to synthesize Ethiopian matriarchal dignity without referencing, imitating, or utilizing the likeness of any real living or deceased individual.

| Attribute | Specification |
| :--- | :--- |
| **Character ID** | `char_grandmother_ayelech` |
| **Age** | Approximately 72 years old |
| **Facial Features** | Deep warm brown skin tone, gentle smile lines radiating from almond-shaped eyes, dignified expression reflecting deep peace, kindness, and ancestral memory. |
| **Hair** | Silver-streaked hair styled in fine traditional braids (*Shuruba*), partially covered by a soft white cotton veil (*Netela*). |
| **Attire** | Authentic handwoven Ethiopian cotton gown (*Habesha Kemis*) in natural off-white, featuring delicate geometric *Tibeb* embroidery in forest green, amber, and gold thread along the neckline and hem. |
| **Hands** | Weathered, capable, graceful hands showing decades of dedicated domestic craft, coffee roasting, and maternal care. |
| **Voice & Persona** | Warm, calm, measured maternal tone; pacing is unhurried, reflecting the patience inherent to traditional life. |

---

## 3. Visual Aesthetic & Camera Direction

- **Cinematic Style**: Warm 35mm film aesthetic evoking documentary realism with poetic intimacy (Kodak Vision3 250D film emulation).
- **Lighting**: Low-angled golden morning sunlight breaking through light mountain haze; indoor scenes illuminated by glowing red charcoal embers (*Kessel*) and natural daylight shafts.
- **Color Palette**:
  - Primary: Raw earthy ochre, terracotta clay, espresso brown, warm charcoal black.
  - Secondary: Vivid highland green (*Ketema* grass), warm amber yellow, ivory cotton white.
- **Optics**: 50mm f/1.4 and 85mm f/1.8 prime lenses with shallow depth of field, creamy background bokeh, and tactile macro details.
- **Negative Prompting**: Modern electronics, synthetic plastics, harsh fluorescent illumination, distorted anatomy, cartoon rendering, Western contemporary clothing.

---

## 4. Ten-Shot Visual & Narrative Breakdown

| Shot | Duration | Scene Description | Amharic Narration | English Subtitle | Camera Motion |
| :---: | :---: | :--- | :--- | :--- | :--- |
| **01** | 7.5s | Misty Wollo highland dawn | ፀሐይ በደጋው ኮረብታዎች ላይ ስትወጣ... | As the sun rises over the highland hills... | Slow forward dolly |
| **02** | 7.5s | Emaye Ayelech in doorway | እያንዳንዱ ቀን አዲስ በረከት ነው... | Each day is a fresh blessing... | Subtle push-in |
| **03** | 7.5s | Washing raw green coffee beans | ቡና በችኮላ አይዘጋጅም... | Coffee cannot be rushed... | Static macro overhead |
| **04** | 7.5s | Roasting beans over charcoal embers | በእሳት ላይ እያረረ መልካም መዓዛው... | As beans release aroma through heat... | Gentle orbit |
| **05** | 7.5s | Grandmother wafting roasting smoke | ይህንን መዓዛ ተቀበሉ... | Receive this aroma of peace... | Slow pan right |
| **06** | 7.5s | Grinding beans in wooden *Mukecha* | የእያንዳንዷ ድብደባ ድምፅ... | The steady rhythm of each strike... | Low-angle tilt |
| **07** | 7.5s | Simmering black clay *Jebena* | በጀበናው ውስጥ የሚፈላው ውሃ... | The water simmering within the Jebena... | Slow pedestal up |
| **08** | 7.5s | Frankincense smoke over *Ketema* grass | የዕጣኑ ጢስ ወደ ሰማይ ሲወጣ... | As incense ascends toward heaven... | Slow tilt up |
| **09** | 7.5s | Expert high pour into *Sini* cups | በአንድነት ተሰብስበን ስንጠጣ... | When we gather to drink as one... | Subtle tracking down |
| **10** | 7.5s | Grandmother's blessing smile | ትውፊት የእኛ ማንነት ነው... | Heritage is our true essence... | Slow zoom out |

*Total duration: 10 shots × 7.5s = 75.0 seconds.*

---

## 5. Music & Sound Design

### Instrumentation
- **Masenqo**: Single-string bowed lute providing expressive, resonant modal motifs in the traditional *Tizita* (nostalgia) scale.
- **Washint**: End-blown bamboo flute providing gentle melodic ornaments that weave through the background.
- **Krar**: Traditional plucked bowl lyre providing rhythmic acoustic foundation.
- **Kebero**: Hand-played double-headed drum setting an unhurried, ceremonial tempo of 68 BPM.

### Dynamic Audio Ducking Architecture
To ensure complete intelligibility of the Amharic speech while preserving the emotional presence of the original soundtrack:
- **Sidechain Compression Threshold**: 0.125
- **Compression Ratio**: 4:1
- **Attack Time**: 20 ms
- **Release Time**: 300 ms
- **Music Attenuation**: -14 dB attenuation during active speech
- **Loudness Normalization**: Master audio normalized to -16 LUFS with -1.5 dB true peak following EBU R128 specifications.

---

## 6. End Card & AI Disclosure Design

- **Duration**: 4.0 seconds.
- **Background**: Matte deep obsidian (`#120e0b`).
- **Typography**: Clean serif title (`#e8d8c8`) with sans-serif body.
- **Title**: `AI Heritage Short`
- **Disclosure Statement**:
  > *"This film was created using an AI filmmaking pipeline honoring cultural preservation. Character Emaye Ayelech is a fictional synthesis of Ethiopian matriarchal heritage. Directed & Orchestrated with Antigravity CLI."*

