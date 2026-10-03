---
name: social-media-post
description: Generate optimized social media posts for Threads, X (Twitter), and LinkedIn. Analyzes platform algorithms, applies best practices, and creates engaging content tailored to each platform. Local skill for Navigator marketing only.
allowed-tools: Read, Write
version: 1.0.0
local-only: true
---

# Social Media Post Generator Skill

Generate platform-optimized social media posts using algorithm insights and best practices.

**Note**: This is a LOCAL skill for Navigator marketing only. NOT included in the plugin distribution.

## When to Invoke

Auto-invoke when user says:
- "Create a Threads post about [topic]"
- "Write a social media post for [announcement]"
- "Generate X post for [feature]"
- "Create LinkedIn announcement for [release]"
- "Write Threads post like option 5"

## What This Does

**Platform-Specific Workflow**:
1. **Analyze Content**: Extract key points, features, value propositions
2. **Apply Platform Rules**: Character limits, formatting, hashtag strategies
3. **Optimize for Algorithm**: Engagement tactics, timing recommendations
4. **Generate Variants**: Multiple options (short, medium, detailed)
5. **Include Metadata**: Character count, hashtag suggestions, posting time

**Platforms Supported**: Threads, X (Twitter), LinkedIn

---

## Platform Specifications

### Threads (Instagram)

**Character Limits**:
- Standard post: 500 characters
- Long-form (with attachment): 10,000 characters
- Display: Shows "Read more" after ~500 chars

**Formatting**:
✅ Bold, italic, underline, strikethrough
✅ Emojis (count toward limit)
✅ Bullet points (using • or -)
✅ Line breaks
❌ No hashtags in Threads (algorithm ignores them)
❌ No clickable links in body (use link preview)

**Media**:
- Images: Up to 10 per post
- Video: Up to 5 minutes
- Link previews: Automatic from URLs

**Algorithm Priorities** (2025):
1. **Engagement** (40%): Likes, comments, shares, reply views
2. **Recency** (30%): Fresh content gets priority
3. **Interest/Relevance** (20%): Based on user's past interactions
4. **Profile Visits** (10%): Likelihood user will click profile

**Best Practices**:
✅ Conversational, authentic tone (not corporate)
✅ Ask open-ended questions
✅ Create discussions, not announcements
✅ Post consistently (1-3x daily)
✅ Use visuals (images/videos boost engagement)
✅ Respond to comments within 1 hour
❌ No direct cross-posts from Instagram/X
❌ Avoid promotional language
❌ No hashtags (they don't work on Threads)

**Optimal Posting Times** (US audience):
- Monday-Friday: 9-11 AM, 1-3 PM, 7-9 PM ET
- Saturday-Sunday: 10 AM-2 PM ET

**Content That Works**:
- Behind-the-scenes insights
- Quick tips and tricks
- Relatable experiences
- Open-ended questions
- Industry discussions
- Memes (if relevant)

---

### X (Twitter)

**Character Limits**:
- Standard tweet: 280 characters
- Premium (Blue): 25,000 characters (displays with "Show more")

**Formatting**:
✅ Emojis
✅ Line breaks (use intentionally)
✅ Mentions (@username)
✅ Hashtags (max 2-3 per tweet)
❌ No rich text formatting

**Media**:
- Images: Up to 4 per tweet
- Video: Up to 2:20 (standard), 10 min (Blue)
- GIFs: 1 per tweet

**Algorithm Priorities** (2025):
1. **Engagement rate** (likes, retweets, replies)
2. **Recency** (fresh tweets prioritized)
3. **Media** (tweets with images/video perform better)
4. **Authenticity** (verified accounts, genuine engagement)

**Best Practices**:
✅ Front-load important info (first 100 chars)
✅ Use line breaks for readability
✅ 1-2 hashtags max (more hurts engagement)
✅ Include visual (image/video)
✅ Tag relevant accounts (when appropriate)
✅ Tweet threads for detailed content
❌ Don't overuse hashtags (looks spammy)
❌ Avoid link-only tweets (add context)

**Optimal Posting Times** (US audience):
- Monday-Friday: 8-10 AM, 12-1 PM, 5-6 PM ET
- Saturday-Sunday: 9 AM-12 PM ET

---

### LinkedIn

**Character Limits**:
- Post: 3,000 characters (shows "see more" after ~140 chars in feed)
- Article: 125,000 characters

**Formatting**:
✅ Emojis (use sparingly)
✅ Bullet points
✅ Line breaks
✅ Bold (using Unicode)
✅ Numbered lists
❌ No official rich text (use workarounds)

**Media**:
- Images: Up to 9 per post
- Video: Up to 10 minutes
- Documents: PDF uploads

**Algorithm Priorities** (2025):
1. **Dwell time** (how long users read your post)
2. **Engagement** (likes, comments, shares)
3. **Relevance** (to user's network and interests)
4. **Personal connections** (1st-degree connections prioritized)

**Best Practices**:
✅ Professional but authentic tone
✅ Hook in first 2 lines (before "see more")
✅ Tell stories, share insights
✅ Use data/statistics
✅ Ask for opinions (engagement)
✅ Tag relevant companies/people
✅ Post 2-5x per week
❌ Avoid overly promotional content
❌ Don't overuse hashtags (3-5 max)

**Optimal Posting Times** (US business hours):
- Tuesday-Thursday: 8-10 AM, 12-1 PM ET
- Avoid: Weekends, late evenings

---

## Workflow Protocol

### Step 1: Content Analysis

**Execute**: `post_analyzer.py`

**Extract**:
- Key announcement/feature
- Value proposition
- Technical details
- Target audience
- Tone (technical, casual, professional)

**Example Input**:
```
Topic: Navigator v3.3.1 with nav-upgrade skill
Key features: One-command updates, automatic configuration
Value: 83% time savings (12 min → 2 min)
Audience: Developers using Claude Code
```

**Output**:
```json
{
  "topic": "Navigator v3.3.1 plugin update automation",
  "key_points": [
    "One-command updates via nav-upgrade skill",
    "Automatic version detection from GitHub",
    "83% time savings",
    "18 total skills"
  ],
  "value_proposition": "Eliminates manual update process",
  "call_to_action": "Install or update Navigator",
  "tone": "technical-casual"
}
```

---

### Step 2: Platform Optimization

**Execute**: `engagement_optimizer.py --platform threads`

**Apply Platform Rules**:
- Character limit enforcement
- Formatting constraints
- Hashtag strategy
- Media recommendations
- CTA placement

**Optimize for Algorithm**:
- Engagement hooks
- Question placement
- Visual suggestions
- Timing recommendations

---

### Step 3: Generate Post Variants

**Create 3 Variants**:

1. **Short & Punchy** (Option 5 style)
   - Under 280 chars (X-compatible)
   - Emoji bullets
   - Clear value props
   - Direct CTA

2. **Medium Detailed**
   - 300-500 chars (Threads standard)
   - More context
   - Multiple CTAs
   - Conversation starter

3. **Long-Form** (Threads attachment / LinkedIn)
   - 800-1500 chars
   - Full story/context
   - Multiple sections
   - Rich formatting

---

### Step 4: Add Metadata

For each variant, include:

```markdown
**Platform**: Threads
**Character Count**: 287/500
**Estimated Engagement**: High (question + visual + emojis)
**Hashtags**: None (Threads doesn't use hashtags)
**Media Suggestion**: Screenshot of update command
**Best Time to Post**: Tuesday 9-11 AM ET
**Follow-up**: Reply with technical details after 2 hours
```

---

## Templates

### Template: Product Launch (Threads)

```
[Hook Question]

[Product Name] [Version] just landed:

✅ [Feature 1]: [Benefit]
✅ [Feature 2]: [Benefit]
✅ [Feature 3]: [Benefit]
✅ [Key Metric]: [Value proposition]

[CTA 1]:
[Command/Installation]

[CTA 2]:
[Command/Update]

[Link]

[Conversation Hook]
```

**Example**:
```
Teach your Claude Code to design like a Product Designer.

Navigator v3.3.1:
✅ Figma MCP (design extraction)
✅ Storybook automation
✅ Chromatic integration
✅ One-command updates

Install:
/plugin marketplace add qf-studio/navigator

Update:
"Update Navigator"

https://github.com/qf-studio/navigator

What's your biggest design handoff pain point?
```

**Character Count**: 289/500
**Engagement Hook**: Opening question + closing question

---

### Template: Feature Announcement (X)

```
[Feature Name] just shipped 🚀

[Key benefit in 1 line]

[Emoji] [Feature detail 1]
[Emoji] [Feature detail 2]
[Emoji] [Feature detail 3]

[CTA with link]

[Optional: Thread continuation →]
```

**Example**:
```
One-command Navigator updates 🚀

No more manual /plugin update, CLAUDE.md editing, or verification.

✅ "Update Navigator"
✅ 2 min vs 12 min manual
✅ 95% success rate

Install: /plugin marketplace add qf-studio/navigator

https://github.com/qf-studio/navigator
```

**Character Count**: 241/280
**Thread continuation**: Technical details, user testimonial, or demo

---

### Template: Technical Deep-Dive (LinkedIn)

```
[Professional Hook - Problem Statement]

[Solution Introduction]

**What we built:**
• [Technical detail 1]
• [Technical detail 2]
• [Technical detail 3]

**The impact:**
[Metric 1]: [Before] → [After] ([Percentage] improvement)
[Metric 2]: [Specific outcome]

**How it works:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

This is what AI-native [domain] looks like: [insight].

[Technical details / GitHub link]

**Thoughts?** [Open-ended question for discussion]

#[Hashtag1] #[Hashtag2] #[Hashtag3]
```

---

## Predefined Functions

### functions/post_analyzer.py

**Purpose**: Extract key points and structure from content

**Usage**:
```bash
python post_analyzer.py --input "Navigator v3.3.1 announcement" --context release-notes.md
```

**Output**:
```json
{
  "topic": "...",
  "key_points": [...],
  "value_proposition": "...",
  "tone": "...",
  "suggested_platforms": ["threads", "x", "linkedin"]
}
```

### functions/engagement_optimizer.py

**Purpose**: Apply platform-specific optimization rules

**Usage**:
```bash
python engagement_optimizer.py --platform threads --content post-draft.md
```

**Output**:
```json
{
  "optimized_content": "...",
  "character_count": 287,
  "engagement_score": 8.5,
  "improvements": [
    "Added opening question for engagement",
    "Replaced hashtags with conversation hook",
    "Added emojis for visual appeal"
  ],
  "warnings": ["Consider adding visual (screenshot/demo)"]
}
```

### functions/thread_generator.py

**Purpose**: Generate multi-post threads for detailed announcements

**Usage**:
```bash
python thread_generator.py --platform x --content full-announcement.md --max-tweets 5
```

**Output**: Structured thread with optimal character distribution

---

## Examples

### Example 1: Quick Feature Announcement (Threads)

**Input**:
```
Generate Threads post for Navigator v3.3.1 nav-upgrade skill, short & punchy style
```

**Output**:
```markdown
**Platform**: Threads
**Style**: Short & Punchy (Option 5)
**Character Count**: 274/500

---

Teach Claude Code to automate like a Pro.

Navigator v3.3.1:
✅ One-command updates
✅ Figma MCP integration
✅ Storybook + Chromatic automation
✅ 18 skills total

"Update Navigator" → Done in 2 min

Install: /plugin marketplace add qf-studio/navigator

https://github.com/qf-studio/navigator

What workflow would you automate next?

---

**Metadata**:
- Engagement Hook: Opening statement + closing question
- Visual Suggestion: Terminal screenshot of "Update Navigator" command
- Best Time: Tuesday 10 AM ET
- Follow-up: Reply with technical details after 2 hours
```

---

### Example 2: Technical Thread (X)

**Input**:
```
Create X thread explaining complete design-to-production pipeline
```

**Output**:
```markdown
**Platform**: X (Twitter)
**Format**: Thread (4 tweets)

---

**Tweet 1/4** (Main)
We just automated the complete design-to-production pipeline.

Figma → Code → Testing in 20 minutes.

Here's how Navigator v3.3.1 makes it work: 🧵👇

(278/280 chars)

---

**Tweet 2/4**
Step 1: Design Extraction

"Review this design from Figma"

Navigator + Figma MCP:
✅ Extracts design tokens (DTCG)
✅ Maps components
✅ Detects drift
✅ Generates plan

15 minutes vs 6-10 hours manually

(195/280 chars)

---

**Tweet 3/4**
Step 2: Visual Regression

"Set up visual regression for Button"

Navigator:
✅ Generates Storybook stories
✅ Configures Chromatic
✅ Creates CI workflows

5 minutes vs 2-3 hours manually

(184/280 chars)

---

**Tweet 4/4**
The result:

Design handoff → Pixel-perfect CI in 20 minutes

All with natural language.
97% token efficiency.
18 skills for complete automation.

Try it: /plugin marketplace add qf-studio/navigator

https://github.com/qf-studio/navigator

(242/280 chars)

---

**Metadata**:
- Total thread length: 4 tweets, 899 chars total
- Engagement: Question/discussion starter in replies
- Visual: Attach architecture diagram to tweet 1
- Best Time: Wednesday 9 AM ET
```

---

## Best Practices by Platform

### Threads
1. **Be conversational**: Avoid corporate speak
2. **Ask questions**: Drive engagement with open-ended questions
3. **No hashtags**: They don't work on Threads
4. **Respond fast**: Reply to comments within 1 hour
5. **Post consistently**: 1-3x daily for best reach
6. **Use visuals**: Images/videos boost engagement significantly
7. **Tell stories**: Personal experiences > announcements

### X (Twitter)
1. **Front-load value**: First 100 chars matter most
2. **Use threads**: Break complex topics into digestible tweets
3. **Limit hashtags**: 1-2 max, more hurts engagement
4. **Add media**: Tweets with images get 150% more engagement
5. **Be concise**: Shorter tweets (200-250 chars) perform better
6. **Time it right**: Post during work hours for tech audience

### LinkedIn
1. **Hook early**: First 2 lines show in feed, make them count
2. **Be professional**: But still authentic and relatable
3. **Use data**: Statistics and metrics boost credibility
4. **Tell stories**: Case studies and experiences resonate
5. **Engage back**: Comment on posts in your niche
6. **Post less, quality more**: 2-5x per week is optimal

---

## Usage Patterns

### Pattern 1: Quick Announcement

```
"Create Threads post for v3.3.1 release, option 5 style"
```

Generates: Short & punchy Threads post with emojis, clear CTAs, character count

### Pattern 2: Multi-Platform Campaign

```
"Generate social media posts for v3.3.1 across Threads, X, and LinkedIn"
```

Generates: Platform-optimized variants for each channel

### Pattern 3: Thread Explanation

```
"Create X thread explaining visual-regression skill workflow"
```

Generates: Multi-tweet thread with optimal character distribution

---

## Engagement Scoring

Posts are scored 1-10 based on:
- **Hook strength** (2 points): Captures attention in first line
- **Value clarity** (2 points): Clear benefit/value proposition
- **Engagement prompts** (2 points): Questions, CTAs
- **Visual appeal** (2 points): Emojis, formatting, media suggestion
- **Platform fit** (2 points): Follows platform best practices

**Score 8-10**: High engagement potential
**Score 5-7**: Moderate, could be improved
**Score 1-4**: Needs significant revision

---

## Version History

- **v1.0.0**: Initial skill for Navigator marketing (Threads, X, LinkedIn support)

---

**Last Updated**: 2025-10-21
**Skill Type**: Local (Navigator marketing only)
**Not included in plugin distribution**
