"""
Management command: seed_roommate_posts

Creates fake student users with completed profiles, individual roommate posts,
and group posts so the Roommates hub looks populated during development.

Usage:
    python manage.py seed_roommate_posts
    python manage.py seed_roommate_posts --clear   # remove seeded data first
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from listings.models import RoommateGroup, RoommateGroupMembership, RoommatePost
from users.models import Role, StudentProfile

SEED_TAG = "seed_"

# ─── Individual students (personal posts) ─────────────────────────────────────

SOLO_STUDENTS = [
    {
        "username": "seed_maya_chen",
        "first_name": "Maya",
        "last_name": "Chen",
        "email": "maya.chen.seed@bc.edu",
        "profile": {
            "preferred_name": "Maya",
            "age": 20,
            "gender": "female",
            "major": "Biology",
            "bio": "Pre-med junior looking for a quiet place to study. Early riser, clean, no parties.",
            "messy_level": 5,
            "guest_level": 2,
            "bedtime": 23,
            "noise_level": 1,
            "smoke": False,
            "drink": 2,
            "party": 1,
            "pets": False,
        },
        "post": {
            "title": "2 girls looking for 2 more roommates",
            "description": "We're two juniors (Biology + Nursing) looking for two more roommates in Chestnut Hill or Brighton. We keep the place clean, are early risers, and prefer a quiet household. Ideal for anyone who studies a lot or has early classes.",
            "housing_status": "need_home",
            "current_group_size": 2,
            "open_spots": 2,
            "budget_min": 1400,
            "budget_max": 1700,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Chestnut Hill, Brighton",
            "is_active": True,
        },
    },
    {
        "username": "seed_james_okafor",
        "first_name": "James",
        "last_name": "Okafor",
        "email": "james.okafor.seed@bc.edu",
        "profile": {
            "preferred_name": "James",
            "age": 21,
            "gender": "male",
            "major": "Finance",
            "bio": "Finance senior interning downtown this summer. Looking for a chill house with people who know how to have fun but also respect quiet time.",
            "messy_level": 3,
            "guest_level": 3,
            "bedtime": 1,
            "noise_level": 3,
            "smoke": False,
            "drink": 3,
            "party": 3,
            "pets": False,
        },
        "post": {
            "title": "3 guys need a 4th for off-campus house",
            "description": "We already have a 4-bed place in Cleveland Circle lined up — just need one more person. We're chill, social on weekends but quiet during the week. Looking for someone who pulls their weight on chores and rent. House has a backyard.",
            "housing_status": "have_home",
            "current_group_size": 3,
            "open_spots": 1,
            "budget_min": 1350,
            "budget_max": 1500,
            "move_in_date": datetime.date(2026, 8, 15),
            "neighborhoods": "Cleveland Circle",
            "is_active": True,
        },
    },
    {
        "username": "seed_priya_nair",
        "first_name": "Priya",
        "last_name": "Nair",
        "email": "priya.nair.seed@bc.edu",
        "profile": {
            "preferred_name": "Priya",
            "age": 19,
            "gender": "female",
            "major": "Computer Science",
            "bio": "Sophomore CS student. Night owl. I code a lot but I'm friendly — just need good wifi and a quiet desk area.",
            "messy_level": 3,
            "guest_level": 2,
            "bedtime": 2,
            "noise_level": 2,
            "smoke": False,
            "drink": 1,
            "party": 1,
            "pets": True,
        },
        "post": {
            "title": "Solo CS student looking to join a group",
            "description": "Sophomore looking for a 3-4 person apartment near campus or on the T. I'm tidy, keep to myself mostly, but down for the occasional hangout. I have a small cat — deal breaker if anyone's allergic. Budget is flexible.",
            "housing_status": "need_home",
            "current_group_size": 1,
            "open_spots": 2,
            "budget_min": 1200,
            "budget_max": 1800,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Chestnut Hill, Newton Centre, Brookline",
            "is_active": True,
        },
    },
    {
        "username": "seed_carlos_reyes",
        "first_name": "Carlos",
        "last_name": "Reyes",
        "email": "carlos.reyes.seed@bc.edu",
        "profile": {
            "preferred_name": "Carlos",
            "age": 22,
            "gender": "male",
            "major": "Political Science",
            "bio": "Senior poli-sci, involved in a lot of on-campus activities. Usually out in the evenings but mornings are quiet. Looking for roommates who are independent and low-drama.",
            "messy_level": 3,
            "guest_level": 4,
            "bedtime": 0,
            "noise_level": 3,
            "smoke": False,
            "drink": 3,
            "party": 2,
            "pets": False,
        },
        "post": {
            "title": "4-person group — 1 spot left in Brighton triple",
            "description": "We have a great triple in Brighton, 10 min walk to the B line. Three of us confirmed, looking for one more easy-going person. Rent is split 4 ways. Place has in-unit laundry and a decent kitchen. Move-in flexible.",
            "housing_status": "have_home",
            "current_group_size": 3,
            "open_spots": 1,
            "budget_min": 1100,
            "budget_max": 1300,
            "move_in_date": datetime.date(2026, 8, 1),
            "neighborhoods": "Brighton, Allston",
            "is_active": True,
        },
    },
    {
        "username": "seed_alex_kim",
        "first_name": "Alex",
        "last_name": "Kim",
        "email": "alex.kim.seed@bc.edu",
        "profile": {
            "preferred_name": "Alex",
            "age": 20,
            "gender": "other",
            "major": "Psychology",
            "bio": "Junior psych major, pretty social but know when to dial it back. Big on keeping shared spaces clean. Looking for roommates who communicate well.",
            "messy_level": 4,
            "guest_level": 3,
            "bedtime": 23,
            "noise_level": 2,
            "smoke": False,
            "drink": 2,
            "party": 2,
            "pets": False,
        },
        "post": {
            "title": "2 roommates searching for apartment + 1 more person",
            "description": "Alex and Sam, both juniors, are looking for a third to round out our apartment search. We want somewhere in Brookline or Newton — ideally 3-bed, under $1700/person. We both value cleanliness and good communication. Come meet us!",
            "housing_status": "need_home",
            "current_group_size": 2,
            "open_spots": 1,
            "budget_min": 1300,
            "budget_max": 1650,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Brookline, Newton",
            "is_active": True,
        },
    },
    {
        "username": "seed_zoe_marchand",
        "first_name": "Zoe",
        "last_name": "Marchand",
        "email": "zoe.marchand.seed@bc.edu",
        "profile": {
            "preferred_name": "Zoe",
            "age": 20,
            "gender": "female",
            "major": "English Literature",
            "bio": "Junior English major, big reader, occasional baker. I'm tidy and keep weird hours sometimes — thesis season is real. Love living with creative people.",
            "messy_level": 4,
            "guest_level": 2,
            "bedtime": 1,
            "noise_level": 2,
            "smoke": False,
            "drink": 2,
            "party": 1,
            "pets": True,
        },
        "post": None,
    },
    {
        "username": "seed_marcus_bell",
        "first_name": "Marcus",
        "last_name": "Bell",
        "email": "marcus.bell.seed@bc.edu",
        "profile": {
            "preferred_name": "Marcus",
            "age": 22,
            "gender": "male",
            "major": "Economics",
            "bio": "Senior econ major, play intramural basketball, pretty easy to live with. Looking for a spot with good transit access — I'm downtown a lot.",
            "messy_level": 3,
            "guest_level": 3,
            "bedtime": 0,
            "noise_level": 3,
            "smoke": False,
            "drink": 3,
            "party": 3,
            "pets": False,
        },
        "post": None,
    },
    {
        "username": "seed_sophie_lin",
        "first_name": "Sophie",
        "last_name": "Lin",
        "email": "sophie.lin.seed@bc.edu",
        "profile": {
            "preferred_name": "Sophie",
            "age": 19,
            "gender": "female",
            "major": "Nursing",
            "bio": "Sophomore nursing student. Clinical rotations mean I'm on weird schedules. I'm very clean and quiet — need good sleep when I can get it.",
            "messy_level": 5,
            "guest_level": 1,
            "bedtime": 22,
            "noise_level": 1,
            "smoke": False,
            "drink": 1,
            "party": 1,
            "pets": False,
        },
        "post": None,
    },
    {
        "username": "seed_ryan_walsh",
        "first_name": "Ryan",
        "last_name": "Walsh",
        "email": "ryan.walsh.seed@bc.edu",
        "profile": {
            "preferred_name": "Ryan",
            "age": 21,
            "gender": "male",
            "major": "Marketing",
            "bio": "Junior marketing major. Social, like having people over on weekends. Pretty chill about most things — just looking for a fun, low-stress house.",
            "messy_level": 2,
            "guest_level": 4,
            "bedtime": 2,
            "noise_level": 4,
            "smoke": False,
            "drink": 4,
            "party": 4,
            "pets": False,
        },
        "post": None,
    },
    {
        "username": "seed_diana_foster",
        "first_name": "Diana",
        "last_name": "Foster",
        "email": "diana.foster.seed@bc.edu",
        "profile": {
            "preferred_name": "Diana",
            "age": 20,
            "gender": "female",
            "major": "Philosophy",
            "bio": "Philosophy junior, part-time barista. I work early mornings so I'm up at 6am — ideal if you're a morning person too. Very clean. Love having a cozy home.",
            "messy_level": 5,
            "guest_level": 2,
            "bedtime": 22,
            "noise_level": 1,
            "smoke": False,
            "drink": 1,
            "party": 1,
            "pets": True,
        },
        "post": None,
    },
]

# ─── Group scenarios ───────────────────────────────────────────────────────────
# Each group has a lead (who creates the group), a list of member usernames,
# a group name/description, and a group post.

GROUP_SCENARIOS = [
    {
        "lead_username": "seed_group_lead_tj",
        "lead": {
            "first_name": "TJ",
            "last_name": "Morrison",
            "email": "tj.morrison.seed@bc.edu",
            "profile": {
                "preferred_name": "TJ",
                "age": 21,
                "gender": "male",
                "major": "Architecture",
                "bio": "Junior architecture student. We're a house of four who met through studio — we all keep late hours and appreciate good design. Looking for a 5th.",
                "messy_level": 3,
                "guest_level": 3,
                "bedtime": 2,
                "noise_level": 2,
                "smoke": False,
                "drink": 3,
                "party": 2,
                "pets": False,
            },
        },
        "members": [
            {
                "username": "seed_group_member_layla",
                "first_name": "Layla",
                "last_name": "Huang",
                "email": "layla.huang.seed@bc.edu",
                "profile": {
                    "preferred_name": "Layla",
                    "age": 21,
                    "gender": "female",
                    "major": "Architecture",
                    "bio": "Architecture junior, studio partner with TJ. Night owl, very tidy in shared spaces.",
                    "messy_level": 4,
                    "guest_level": 2,
                    "bedtime": 2,
                    "noise_level": 2,
                    "smoke": False,
                    "drink": 2,
                    "party": 2,
                    "pets": False,
                },
            },
            {
                "username": "seed_group_member_omar",
                "first_name": "Omar",
                "last_name": "Saleh",
                "email": "omar.saleh.seed@bc.edu",
                "profile": {
                    "preferred_name": "Omar",
                    "age": 22,
                    "gender": "male",
                    "major": "Architecture",
                    "bio": "Senior arch student. Quiet when working, fun when not. Cook a lot — love a good kitchen.",
                    "messy_level": 4,
                    "guest_level": 3,
                    "bedtime": 1,
                    "noise_level": 2,
                    "smoke": False,
                    "drink": 2,
                    "party": 2,
                    "pets": False,
                },
            },
            {
                "username": "seed_group_member_becca",
                "first_name": "Becca",
                "last_name": "Novak",
                "email": "becca.novak.seed@bc.edu",
                "profile": {
                    "preferred_name": "Becca",
                    "age": 20,
                    "gender": "female",
                    "major": "Fine Arts",
                    "bio": "Sophomore fine arts. Messy in my room, tidy everywhere else. Creative household is a plus.",
                    "messy_level": 2,
                    "guest_level": 3,
                    "bedtime": 1,
                    "noise_level": 3,
                    "smoke": False,
                    "drink": 2,
                    "party": 2,
                    "pets": True,
                },
            },
        ],
        "group": {
            "name": "Studio House Co.",
            "description": "Four architecture and arts students forming a household. We all keep creative hours, respect each other's work time, and cook together on weekends.",
        },
        "post": {
            "title": "4-person creative household needs a 5th",
            "description": "We're four art/arch students who met through studio and decided to live together. We're looking for a 5-bed near the B or C line — ideally with space for a drafting table or two. We cook communal dinners twice a week and do our own thing otherwise. Looking for someone low-drama who won't mind the occasional late-night project crunch.",
            "housing_status": "need_home",
            "open_spots": 1,
            "budget_min": 1300,
            "budget_max": 1600,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Brookline, Allston, Brighton",
            "is_active": True,
        },
    },
    {
        "lead_username": "seed_group_lead_nia",
        "lead": {
            "first_name": "Nia",
            "last_name": "Thompson",
            "email": "nia.thompson.seed@bc.edu",
            "profile": {
                "preferred_name": "Nia",
                "age": 22,
                "gender": "female",
                "major": "Communications",
                "bio": "Senior comm major. Very social but also know when to be quiet. We have a great group of 3 and already found a 4-bed — need one more.",
                "messy_level": 3,
                "guest_level": 4,
                "bedtime": 1,
                "noise_level": 3,
                "smoke": False,
                "drink": 3,
                "party": 3,
                "pets": False,
            },
        },
        "members": [
            {
                "username": "seed_group_member_jade",
                "first_name": "Jade",
                "last_name": "Rivera",
                "email": "jade.rivera.seed@bc.edu",
                "profile": {
                    "preferred_name": "Jade",
                    "age": 21,
                    "gender": "female",
                    "major": "Sociology",
                    "bio": "Junior sociology major. Pretty social, love having people over. Tidy enough.",
                    "messy_level": 3,
                    "guest_level": 4,
                    "bedtime": 1,
                    "noise_level": 3,
                    "smoke": False,
                    "drink": 3,
                    "party": 3,
                    "pets": False,
                },
            },
            {
                "username": "seed_group_member_cam",
                "first_name": "Cameron",
                "last_name": "Brooks",
                "email": "cam.brooks.seed@bc.edu",
                "profile": {
                    "preferred_name": "Cam",
                    "age": 21,
                    "gender": "other",
                    "major": "Media Studies",
                    "bio": "Media studies junior, big into film. Great with shared spaces. Down for movie nights.",
                    "messy_level": 3,
                    "guest_level": 3,
                    "bedtime": 1,
                    "noise_level": 2,
                    "smoke": False,
                    "drink": 2,
                    "party": 3,
                    "pets": False,
                },
            },
        ],
        "group": {
            "name": "The Comm House",
            "description": "Three communications and social science seniors who've lived together before. We have a place in Cleveland Circle — just need one more person to fill the last room.",
        },
        "post": {
            "title": "Cleveland Circle 4-bed — 1 room open",
            "description": "We're three seniors who've lived together before and have a 4-bed in Cleveland Circle already locked in. The last room is yours. It's a nice place — big kitchen, good natural light, 5-min walk to the C line. We host friends sometimes on weekends but are totally normal during the week. Looking for someone social but not chaotic. DM us!",
            "housing_status": "have_home",
            "open_spots": 1,
            "budget_min": 1400,
            "budget_max": 1600,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Cleveland Circle, Chestnut Hill",
            "is_active": True,
        },
    },
    {
        "lead_username": "seed_group_lead_ethan",
        "lead": {
            "first_name": "Ethan",
            "last_name": "Park",
            "email": "ethan.park.seed@bc.edu",
            "profile": {
                "preferred_name": "Ethan",
                "age": 20,
                "gender": "male",
                "major": "Data Science",
                "bio": "Sophomore data science. Remote internship this summer, so I'll be home a lot. Very tidy, respectful of shared spaces. Looking to build a solid household from scratch.",
                "messy_level": 5,
                "guest_level": 2,
                "bedtime": 23,
                "noise_level": 2,
                "smoke": False,
                "drink": 1,
                "party": 1,
                "pets": False,
            },
        },
        "members": [
            {
                "username": "seed_group_member_nina",
                "first_name": "Nina",
                "last_name": "Patel",
                "email": "nina.patel.seed@bc.edu",
                "profile": {
                    "preferred_name": "Nina",
                    "age": 20,
                    "gender": "female",
                    "major": "Statistics",
                    "bio": "Sophomore stats major. Study a lot, quiet household preferred. Clean and organized.",
                    "messy_level": 5,
                    "guest_level": 1,
                    "bedtime": 23,
                    "noise_level": 1,
                    "smoke": False,
                    "drink": 1,
                    "party": 1,
                    "pets": False,
                },
            },
        ],
        "group": {
            "name": "Quiet House 2026",
            "description": "Two data/stats sophomores looking to build a quiet, study-focused household of 3-4 people. Good internet, clean space, early-ish bedtimes.",
        },
        "post": {
            "title": "Quiet study household — 2 spots open",
            "description": "Two sophomores (data science + stats) building a small quiet household from scratch. We're looking for a 3 or 4-bed apartment in Newton or Brookline — good transit, safe neighborhood. We both work a lot during the week and value a clean, calm home. Ideal housemates are organized, considerate, and not loud. No smoking. Pets negotiable.",
            "housing_status": "need_home",
            "open_spots": 2,
            "budget_min": 1250,
            "budget_max": 1550,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Newton, Brookline, Chestnut Hill",
            "is_active": True,
        },
    },
    {
        "lead_username": "seed_group_lead_mia",
        "lead": {
            "first_name": "Mia",
            "last_name": "Castellano",
            "email": "mia.castellano.seed@bc.edu",
            "profile": {
                "preferred_name": "Mia",
                "age": 21,
                "gender": "female",
                "major": "Business Administration",
                "bio": "Junior business major. I run a pretty tight household — chore charts, grocery sharing, the works. If you like organization, you'll love living with us.",
                "messy_level": 5,
                "guest_level": 3,
                "bedtime": 23,
                "noise_level": 2,
                "smoke": False,
                "drink": 2,
                "party": 2,
                "pets": False,
            },
        },
        "members": [
            {
                "username": "seed_group_member_sara",
                "first_name": "Sara",
                "last_name": "Donovan",
                "email": "sara.donovan.seed@bc.edu",
                "profile": {
                    "preferred_name": "Sara",
                    "age": 21,
                    "gender": "female",
                    "major": "Accounting",
                    "bio": "Junior accounting. Very organized, not a partier. Looking for a clean, functional home.",
                    "messy_level": 5,
                    "guest_level": 2,
                    "bedtime": 23,
                    "noise_level": 1,
                    "smoke": False,
                    "drink": 2,
                    "party": 1,
                    "pets": False,
                },
            },
            {
                "username": "seed_group_member_rachel",
                "first_name": "Rachel",
                "last_name": "Cho",
                "email": "rachel.cho.seed@bc.edu",
                "profile": {
                    "preferred_name": "Rachel",
                    "age": 20,
                    "gender": "female",
                    "major": "Finance",
                    "bio": "Sophomore finance. Interning this summer. Very neat. Prefer a quieter home environment.",
                    "messy_level": 5,
                    "guest_level": 2,
                    "bedtime": 23,
                    "noise_level": 2,
                    "smoke": False,
                    "drink": 2,
                    "party": 1,
                    "pets": False,
                },
            },
        ],
        "group": {
            "name": "CSOM House",
            "description": "Three business school students who want a well-run, clean household near campus. We use a shared chore chart, split groceries, and keep the place tidy. Looking for a 4th with the same mindset.",
        },
        "post": {
            "title": "CSOM students need 1 more — organized household",
            "description": "Three business school juniors forming a household for 2026–27. We've lived together before (two of us) and we run a pretty organized home — chore chart, shared grocery fund, house rules on the fridge. It works. Looking for a 4th who's similarly clean and drama-free. We're searching for a 4-bed in Chestnut Hill or Newton, under $1600/person.",
            "housing_status": "need_home",
            "open_spots": 1,
            "budget_min": 1350,
            "budget_max": 1600,
            "move_in_date": datetime.date(2026, 9, 1),
            "neighborhoods": "Chestnut Hill, Newton, Brookline",
            "is_active": True,
        },
    },
]


def _make_user(User, username, first_name, last_name, email):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "role": Role.STUDENT,
            "is_active": True,
            "profile_completed_at": timezone.now(),
        },
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user, created


def _make_profile(user, p):
    StudentProfile.objects.update_or_create(
        user=user,
        defaults={
            "preferred_name": p["preferred_name"],
            "age": p["age"],
            "gender": p["gender"],
            "major": p["major"],
            "bio": p["bio"],
            "messy_level": p["messy_level"],
            "guest_level": p["guest_level"],
            "bedtime": p["bedtime"],
            "noise_level": p["noise_level"],
            "smoke": p["smoke"],
            "drink": p["drink"],
            "party": p["party"],
            "pets": p["pets"],
        },
    )


class Command(BaseCommand):
    help = "Seed fake roommate posts and groups for development/demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously seeded users and data before re-seeding.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if options["clear"]:
            deleted, _ = User.objects.filter(username__startswith=SEED_TAG).delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} seeded user(s) and related data."))

        # ── Solo students ──────────────────────────────────────────────────────
        self.stdout.write("\n--- Solo students ---")
        solo_count = 0
        for data in SOLO_STUDENTS:
            user, created = _make_user(User, data["username"], data["first_name"], data["last_name"], data["email"])
            if not created:
                self.stdout.write(f"  skipped (exists): {user.username}")
                continue

            _make_profile(user, data["profile"])

            if data.get("post"):
                rp = data["post"]
                RoommatePost.objects.get_or_create(
                    author=user,
                    defaults={
                        "title": rp["title"],
                        "description": rp["description"],
                        "housing_status": rp["housing_status"],
                        "current_group_size": rp["current_group_size"],
                        "open_spots": rp["open_spots"],
                        "budget_min": rp["budget_min"],
                        "budget_max": rp["budget_max"],
                        "move_in_date": rp["move_in_date"],
                        "neighborhoods": rp["neighborhoods"],
                        "is_active": rp["is_active"],
                    },
                )
                self.stdout.write(self.style.SUCCESS(f"  created: {user.get_full_name()} + post"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  created: {user.get_full_name()} (no post)"))

            solo_count += 1

        # ── Group scenarios ────────────────────────────────────────────────────
        self.stdout.write("\n--- Group scenarios ---")
        group_count = 0
        for scenario in GROUP_SCENARIOS:
            # Create lead
            lead_data = scenario["lead"]
            lead, lead_created = _make_user(
                User,
                scenario["lead_username"],
                lead_data["first_name"],
                lead_data["last_name"],
                lead_data["email"],
            )
            if not lead_created:
                self.stdout.write(f"  skipped group (lead exists): {lead.username}")
                continue

            _make_profile(lead, lead_data["profile"])

            # Create member users
            member_users = []
            for m in scenario["members"]:
                member, _ = _make_user(User, m["username"], m["first_name"], m["last_name"], m["email"])
                _make_profile(member, m["profile"])
                member_users.append(member)

            # Create group
            g = scenario["group"]
            group, _ = RoommateGroup.objects.get_or_create(
                lead=lead,
                defaults={"name": g["name"], "description": g["description"], "is_active": True},
            )

            # Add lead + members (skip clean() — management command context)
            RoommateGroupMembership.objects.get_or_create(group=group, user=lead)
            for member in member_users:
                RoommateGroupMembership.objects.get_or_create(group=group, user=member)

            # Create group post
            rp = scenario["post"]
            member_count = 1 + len(member_users)
            RoommatePost.objects.get_or_create(
                group=group,
                defaults={
                    "title": rp["title"],
                    "description": rp["description"],
                    "housing_status": rp["housing_status"],
                    "current_group_size": member_count,
                    "open_spots": rp["open_spots"],
                    "budget_min": rp["budget_min"],
                    "budget_max": rp["budget_max"],
                    "move_in_date": rp["move_in_date"],
                    "neighborhoods": rp["neighborhoods"],
                    "is_active": rp["is_active"],
                },
            )

            all_names = ", ".join([lead.first_name] + [m.first_name for m in member_users])
            self.stdout.write(
                self.style.SUCCESS(f"  created group '{g['name']}' ({member_count} members: {all_names}) + post")
            )
            group_count += 1

        self.stdout.write(self.style.SUCCESS(f"\nDone. {solo_count} solo student(s), {group_count} group(s) seeded."))
