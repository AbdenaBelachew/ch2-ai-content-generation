# AI Heritage Short — Ethics, Disclosure & Cultural Integrity

## 1. Principles of Cultural Heritage Representation

The **AI Heritage Short** pipeline is developed with deep reverence for Ethiopian cultural traditions, specifically the sacred social ritual of the Ethiopian coffee ceremony (*Buna*). 

To ensure authentic and respectful representation:
1. **Linguistic Authenticity**: Narration is authored directly in natural Amharic using canonical Ge'ez Fidel orthography, expressing genuine cultural idioms rather than literal machine-translated English idioms.
2. **Procedural Fidelity**: The ten shots depict the authentic ritual sequence recognized across Ethiopian communities: washing green beans $\to$ roasting on charcoal (*Baret Metad*) $\to$ sharing aroma (*Itan*) $\to$ grinding in mortar (*Mukecha*) $\to$ brewing in clay pot (*Jebena*) $\to$ scattering fresh grass (*Ketema*) $\to$ the high pour into handle-less ceramic cups (*Sini*).
3. **Indigenous Soundscapes**: The soundtrack prompt explicitly mandates authentic Ethiopian acoustic instruments (*Masenqo*, *Washint*, *Krar*, *Kebero*) in traditional modal scales (*Tizita*), deliberately avoiding generic synthetic lounge or Westernized approximations.

---

## 2. Character Fictionality & Likeness Protection

> [!IMPORTANT]
> The central protagonist, **Emaye Ayelech**, is an entirely fictional synthesis of Ethiopian matriarchal dignity.
> - No real individual's likeness, face, or photograph was used to train, condition, or reference the character.
> - No living or deceased person's voice was cloned, synthesized, or mimicked without documented consent.
> - The character reference contract (`schema/storyboard.schema.json`) requires explicit documentation if real likenesses are ever introduced in the future.

---

## 3. Transparent AI Disclosure End Card

In accordance with ethical AI filmmaking standards, both 16:9 and 9:16 exports feature a mandatory 4-second concluding end card:

- **Visibility**: Rendered in high-contrast legible typography centered on screen.
- **Copy**:
  > *"This film was created using an AI filmmaking pipeline honoring cultural preservation. Character Emaye Ayelech is a fictional synthesis of Ethiopian matriarchal heritage. Directed & Orchestrated with Antigravity CLI."*
- **No Deceptive Realism**: The short film presents itself openly as an AI-orchestrated artistic work in service of cultural heritage preservation.

---

## 4. Environmental Responsibility Through Caching

Generative AI video diffusion and multi-step transformer inference carry non-trivial compute footprints. 

The pipeline embeds sustainability directly into its architecture via **content-addressed caching** (`pipeline/cache.py`):
- When a shot, subtitle, or sound mix is revised, unchanged video clips and audio stems are **never** re-rendered.
- Unit tests run completely offline with mocks, consuming zero GPU hours or external electricity for verification.

