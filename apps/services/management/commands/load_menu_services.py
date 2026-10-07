from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.services.models import Service, ServiceCategory


MENU_DATA = [
    {
        "category": "Nail Care",
        "description": "Classic and gel nail cleaning, enhancements, and extensions.",
        "services": [
            {
                "name": "Express Cleaning",
                "price": Decimal("100.00"),
                "duration_minutes": 30,
                "description": "A swift nail cleaning service that features nail shaping, buffing, and a complimentary local polish finish.",
            },
            {
                "name": "Classic Manicure",
                "price": Decimal("140.00"),
                "duration_minutes": 45,
                "description": "Basic nail cleaning services include nail shaping, buffing and cuticle cleaning.",
            },
            {
                "name": "Classic Pedicure",
                "price": Decimal("180.00"),
                "duration_minutes": 45,
                "description": "Includes nail shaping, buffing, removal of dead skin, ingrown and cuticle cleaning.",
            },
            {
                "name": "Gel Manicure",
                "price": Decimal("500.00"),
                "duration_minutes": 60,
                "description": "Signature dry manicure cleaning with one shade of gel polish on natural nails.",
            },
            {
                "name": "Gel Pedicure",
                "price": Decimal("550.00"),
                "duration_minutes": 60,
                "description": "Signature dry pedicure with one shade of gel polish on natural nails.",
            },
            {
                "name": "Soft Gel Extension",
                "price": Decimal("1200.00"),
                "duration_minutes": 90,
                "description": "Signature dry manicure with full tip extension and one shade of gel polish.",
            },
            {
                "name": "Gel Removal",
                "price": Decimal("120.00"),
                "duration_minutes": 30,
                "description": "Removal of gel polish. (* OUR WORK = FREE REMOVAL)",
            },
            {
                "name": "Extension Removal",
                "price": Decimal("300.00"),
                "duration_minutes": 30,
                "description": "Removal of nail extension. (* OUR WORK = LESS 50, * OUR WORK + NEW SET = LESS 100)",
            },
        ],
    },
    {
        "category": "Russian / E-File Cleaning",
        "description": "Advanced e-file cuticle care and structured gel enhancements.",
        "services": [
            {
                "name": "Russian Manicure",
                "price": Decimal("1200.00"),
                "duration_minutes": 120,
                "description": "Russian Manicure cleaning using advanced e-file technique for precise cuticle care.",
            },
            {
                "name": "Russian Manicure + Gel Polish",
                "price": Decimal("1500.00"),
                "duration_minutes": 120,
                "description": "Russian Manicure cleaning with one shade of solid or sheer gel polish.",
            },
            {
                "name": "Russian Manicure + Soft Builder Gel",
                "price": Decimal("1800.00"),
                "duration_minutes": 150,
                "description": "A detailed dry cuticle cleaning and soft builder gel overlay for added structure and durability. Provides a natural, flexible finish, ideal for healthy, strong nails. (+ 200 Solid Gel Application)",
            },
            {
                "name": "Russian Manicure + Hard Builder Gel",
                "price": Decimal("2000.00"),
                "duration_minutes": 150,
                "description": "Strong, more structured, and longer-lasting. Recommended for clients with weak, brittle, or easily breaking nails who need extra reinforcement. (+ 200 Solid Gel Application)",
            },
            {
                "name": "Russian Pedicure",
                "price": Decimal("1500.00"),
                "duration_minutes": 120,
                "description": "Russian Pedicure cleaning using advanced e-file technique for precise cuticle care.",
            },
            {
                "name": "Russian Pedicure + Gel Polish",
                "price": Decimal("2000.00"),
                "duration_minutes": 120,
                "description": "Russian Pedicure cleaning with one shade of solid or sheer gel polish.",
            },
            {
                "name": "Russian Pedicure + Gel Polish Callous Removal",
                "price": Decimal("2500.00"),
                "duration_minutes": 150,
                "description": "Detailed toenail cleaning, combined with gentle callus removal to smooth rough skin and leave feet looking clean, refined, and well-groomed. (+ 400 Builder Gel)",
            },
            {
                "name": "Russian Pedicure + Gel Polish Reconstruction + Callous Removal",
                "price": Decimal("3500.00"),
                "duration_minutes": 180,
                "description": "Detailed toenail cleaning, followed by a builder gel application for added strength, structure, and long-lasting, well-groomed results. (+ 200 Solid Gel Application)",
            },
            {
                "name": "Softgel / Builder Gel Removal",
                "price": Decimal("300.00"),
                "duration_minutes": 30,
                "description": "Safe removal of softgel or builder gel enhancements. (* OUR WORK = FREE REMOVAL)",
            },
        ],
    },
    {
        "category": "Promo Packages",
        "description": "Value bundles and combo packages offering up to 20% discount.",
        "services": [
            {
                "name": "GN1",
                "price": Decimal("370.00"),
                "duration_minutes": 60,
                "description": "Classic Manicure + Classic Pedicure, Eyebrow Threading",
            },
            {
                "name": "GN2",
                "price": Decimal("400.00"),
                "duration_minutes": 60,
                "description": "Classic Manicure + Classic Pedicure, Ear Candling",
            },
            {
                "name": "GN3",
                "price": Decimal("450.00"),
                "duration_minutes": 60,
                "description": "Classic Manicure + Classic Pedicure, Underarm Wax",
            },
            {
                "name": "GN4",
                "price": Decimal("470.00"),
                "duration_minutes": 75,
                "description": "Classic Manicure + Classic Pedicure, Foot Spa",
            },
            {
                "name": "GN5",
                "price": Decimal("550.00"),
                "duration_minutes": 75,
                "description": "Classic Pedicure + Foot Spa, Foot Massage (30 mins). (+ 100 upgrade to Reflexology 45 mins)",
            },
            {
                "name": "GN6",
                "price": Decimal("600.00"),
                "duration_minutes": 75,
                "description": "Gel Manicure + Classic Pedicure. (+ 50 switch Gel Manicure to Gel Pedicure)",
            },
            {
                "name": "GN7",
                "price": Decimal("650.00"),
                "duration_minutes": 90,
                "description": "Classic Manicure + Classic Pedicure, Foot Spa + Foot Massage (30 mins). (+ 100 upgrade to Reflexology 45 mins)",
            },
            {
                "name": "GN8",
                "price": Decimal("700.00"),
                "duration_minutes": 75,
                "description": "Classic Manicure + Classic Pedicure, Eyelash Lift",
            },
            {
                "name": "GN9",
                "price": Decimal("750.00"),
                "duration_minutes": 60,
                "description": "Gel Pedicure, Foot Spa",
            },
            {
                "name": "GN10",
                "price": Decimal("800.00"),
                "duration_minutes": 75,
                "description": "Gel Manicure + Classic Pedicure, Foot Spa. (+ 50 switch Gel Manicure to Gel Pedicure)",
            },
            {
                "name": "GN11",
                "price": Decimal("950.00"),
                "duration_minutes": 75,
                "description": "Gel Manicure, Gel Pedicure",
            },
            {
                "name": "GN12",
                "price": Decimal("1200.00"),
                "duration_minutes": 90,
                "description": "Gel Manicure + Gel Pedicure, Foot Spa",
            },
            {
                "name": "GN13",
                "price": Decimal("1300.00"),
                "duration_minutes": 90,
                "description": "Gel Manicure + Classic Pedicure, Classic Lash Extension. (+ 200 Upgrade to Full Classic Lash Extension)",
            },
            {
                "name": "GN14",
                "price": Decimal("1500.00"),
                "duration_minutes": 120,
                "description": "Classic Pedicure + Foot Spa, Softgel Nail Extension",
            },
            {
                "name": "GN15",
                "price": Decimal("1700.00"),
                "duration_minutes": 120,
                "description": "Gel Pedicure, Softgel Nail Extension",
            },
            {
                "name": "GN16",
                "price": Decimal("2000.00"),
                "duration_minutes": 120,
                "description": "Wet Look Lash Extension, Softgel Nail Extension",
            },
        ],
    },
    {
        "category": "Spa & Massage",
        "description": "Relaxing pampering treatments for hands, feet, and body.",
        "services": [
            {
                "name": "Hand Spa",
                "price": Decimal("300.00"),
                "duration_minutes": 30,
                "description": "This treatment includes a hand scrub, a moisturizing mask, and a brief massage.",
            },
            {
                "name": "Hand Massage",
                "price": Decimal("250.00"),
                "duration_minutes": 30,
                "description": "A soothing treatment that includes a gentle massage of the hands and forearms, designed to relieve tension and improve circulation.",
            },
            {
                "name": "Reflexology",
                "price": Decimal("350.00"),
                "duration_minutes": 45,
                "description": "This treatment features a 30-minute foot massage, a 10-minute hand massage, and a 5-minute dry back massage.",
            },
            {
                "name": "Ear Candling",
                "price": Decimal("200.00"),
                "duration_minutes": 30,
                "description": "A gentle ear candling treatment to relieve pressure and promote relaxation.",
            },
            {
                "name": "Foot Spa",
                "price": Decimal("300.00"),
                "duration_minutes": 45,
                "description": "This treatment involves cleaning of dead skin and calluses, a foot scrub, a nourishing mask, and a brief massage.",
            },
            {
                "name": "Foot Massage",
                "price": Decimal("250.00"),
                "duration_minutes": 30,
                "description": "A calming foot massage that relieves tension and promotes relaxation through gentle pressure.",
            },
            {
                "name": "Paraffin Wax",
                "price": Decimal("300.00"),
                "duration_minutes": 30,
                "description": "This luxurious procedure enhances circulation and leaves your skin feeling irresistibly smooth and revitalized.",
            },
            {
                "name": "Ear Candling w/ Head Massage",
                "price": Decimal("400.00"),
                "duration_minutes": 45,
                "description": "Ear candling combined with a soothing head massage.",
            },
        ],
    },
    {
        "category": "Kiddie Nails",
        "description": "Gentle nail care, foot spa, and massage tailored for children.",
        "services": [
            {
                "name": "Express Cleaning",
                "price": Decimal("80.00"),
                "duration_minutes": 20,
                "description": "A swift, gentle nail cleaning and trimming service for kids.",
            },
            {
                "name": "Kiddie Manicure",
                "price": Decimal("100.00"),
                "duration_minutes": 30,
                "description": "Gentle manicure cleaning, trimming, and shaping for kids.",
            },
            {
                "name": "Kiddie Pedicure",
                "price": Decimal("100.00"),
                "duration_minutes": 30,
                "description": "Gentle pedicure cleaning, trimming, and shaping for kids.",
            },
            {
                "name": "Kiddie Massage",
                "price": Decimal("150.00"),
                "duration_minutes": 30,
                "description": "A gentle and calming massage specially tailored for kids.",
            },
            {
                "name": "Kiddie Hand Spa",
                "price": Decimal("200.00"),
                "duration_minutes": 30,
                "description": "Gentle hand scrub, moisturizing mask, and light massage for kids.",
            },
            {
                "name": "Kiddie Foot Spa",
                "price": Decimal("200.00"),
                "duration_minutes": 30,
                "description": "Gentle foot soak, scrub, nourishing mask, and light massage for kids.",
            },
            {
                "name": "KN1",
                "price": Decimal("180.00"),
                "duration_minutes": 45,
                "description": "Kiddie Manicure, Kiddie Pedicure",
            },
            {
                "name": "KN2",
                "price": Decimal("250.00"),
                "duration_minutes": 45,
                "description": "Kiddie Pedicure, Foot Spa",
            },
            {
                "name": "KN3",
                "price": Decimal("300.00"),
                "duration_minutes": 60,
                "description": "Kiddie Manicure, Kiddie Pedicure, Kiddie Foot Massage",
            },
            {
                "name": "KN4",
                "price": Decimal("350.00"),
                "duration_minutes": 60,
                "description": "Kiddie Manicure, Kiddie Pedicure, Kiddie Foot Spa",
            },
        ],
    },
    {
        "category": "Add Ons",
        "description": "Specialty polish, quick-dry coats, and nail strengthening treatments.",
        "services": [
            {
                "name": "Local Nail Polish",
                "price": Decimal("25.00"),
                "duration_minutes": 15,
                "description": "Application of local nail polish.",
            },
            {
                "name": "Imported Nail Polish",
                "price": Decimal("60.00"),
                "duration_minutes": 15,
                "description": "Application of imported premium nail polish.",
            },
            {
                "name": "Orly Top 2 Bottom Top Coat",
                "price": Decimal("50.00"),
                "duration_minutes": 15,
                "description": "Orly Top 2 Bottom base and top coat protective finish.",
            },
            {
                "name": "Orly Sec' N Dry",
                "price": Decimal("50.00"),
                "duration_minutes": 15,
                "description": "Orly Sec' N Dry quick dry finish.",
            },
            {
                "name": "Orly Nailtrition",
                "price": Decimal("50.00"),
                "duration_minutes": 15,
                "description": "Orly Nailtrition nail strengthener treatment.",
            },
            {
                "name": "Cuccio Quick Dry Top Coat",
                "price": Decimal("50.00"),
                "duration_minutes": 15,
                "description": "Cuccio quick dry top coat finish.",
            },
        ],
    },
    {
        "category": "Nail Art",
        "description": "Custom creative designs, chrome, 3D, and hand-painted nail artistry.",
        "services": [
            {
                "name": "Chrome (Per Nail)",
                "price": Decimal("30.00"),
                "duration_minutes": 10,
                "description": "Chrome finish accent on a single nail (PHP 30/nail).",
            },
            {
                "name": "Chrome (Full Set)",
                "price": Decimal("150.00"),
                "duration_minutes": 30,
                "description": "Chrome finish for a complete full set (PHP 150).",
            },
            {
                "name": "Magnetic or Cat Eye (Per Nail)",
                "price": Decimal("30.00"),
                "duration_minutes": 10,
                "description": "Magnetic / Cat Eye effect accent on a single nail (PHP 30/nail).",
            },
            {
                "name": "Magnetic or Cat Eye (Full Set)",
                "price": Decimal("150.00"),
                "duration_minutes": 30,
                "description": "Magnetic / Cat Eye effect for a complete full set (PHP 150).",
            },
            {
                "name": "Embossed / 3D (Per Nail)",
                "price": Decimal("30.00"),
                "duration_minutes": 15,
                "description": "Embossed 3D nail art (PHP 20 - 40 per nail depending on design complexity).",
            },
            {
                "name": "French Tip",
                "price": Decimal("300.00"),
                "duration_minutes": 30,
                "description": "Classic or modern French tip design (PHP 150 - 300 depending on design).",
            },
            {
                "name": "Basic Nail Art Set",
                "price": Decimal("250.00"),
                "duration_minutes": 30,
                "description": "Basic hand-painted nail art set (PHP 150 - 400 depending on complexity).",
            },
            {
                "name": "Intricate Nail Art Set",
                "price": Decimal("500.00"),
                "duration_minutes": 60,
                "description": "Intricate, detailed custom nail art set (PHP 400 - 800 depending on complexity).",
            },
        ],
    },
    {
        "category": "Hands & Feet",
        "description": "Combination manicures, pedicures, foot reflex, and paraffin treatments.",
        "services": [
            {
                "name": "Basic Manicure + Hand Massage",
                "price": Decimal("350.00"),
                "duration_minutes": 45,
                "description": "Basic manicure combined with a soothing hand massage.",
            },
            {
                "name": "Basic Manicure + Hand Spa",
                "price": Decimal("380.00"),
                "duration_minutes": 60,
                "description": "Basic manicure paired with a nourishing hand spa scrub and mask.",
            },
            {
                "name": "Basic Manicure + Hand Paraffin",
                "price": Decimal("380.00"),
                "duration_minutes": 60,
                "description": "Basic manicure finished with warm, deeply moisturizing paraffin wax.",
            },
            {
                "name": "Hand Spa + Hand Massage",
                "price": Decimal("450.00"),
                "duration_minutes": 60,
                "description": "Complete hand spa treatment and relaxing hand massage.",
            },
            {
                "name": "Basic Pedicure + Foot Massage",
                "price": Decimal("380.00"),
                "duration_minutes": 60,
                "description": "Basic pedicure combined with a soothing foot massage.",
            },
            {
                "name": "Basic Pedicure + Foot Spa",
                "price": Decimal("400.00"),
                "duration_minutes": 60,
                "description": "Basic pedicure paired with exfoliating and relaxing foot spa care.",
            },
            {
                "name": "Basic Pedicure + Foot Reflex",
                "price": Decimal("470.00"),
                "duration_minutes": 75,
                "description": "Basic pedicure accompanied by pressure-point foot reflexology.",
            },
            {
                "name": "Foot Spa + Foot Massage",
                "price": Decimal("500.00"),
                "duration_minutes": 75,
                "description": "Revitalizing foot spa treatment with extended relaxing foot massage.",
            },
        ],
    },
    {
        "category": "Waxing",
        "description": "Gentle hair removal waxing and grooming treatments.",
        "services": [
            {
                "name": "Ear Candling",
                "price": Decimal("200.00"),
                "duration_minutes": 30,
                "description": "Gentle ear candling relaxation treatment.",
            },
            {
                "name": "Eyebrow Threading",
                "price": Decimal("150.00"),
                "duration_minutes": 20,
                "description": "Precise eyebrow shaping using threading technique.",
            },
            {
                "name": "Eyebrow Wax",
                "price": Decimal("200.00"),
                "duration_minutes": 20,
                "description": "Clean and gentle eyebrow hair removal wax.",
            },
            {
                "name": "Upper or Lower Lip",
                "price": Decimal("150.00"),
                "duration_minutes": 15,
                "description": "Gentle facial hair removal for upper or lower lip.",
            },
            {
                "name": "Underarm",
                "price": Decimal("250.00"),
                "duration_minutes": 30,
                "description": "Smooth and long-lasting underarm hair removal wax.",
            },
            {
                "name": "Half Arm or Half Leg",
                "price": Decimal("450.00"),
                "duration_minutes": 30,
                "description": "Half arm or half leg hair removal wax treatment.",
            },
            {
                "name": "Full Arm or Full Leg",
                "price": Decimal("750.00"),
                "duration_minutes": 45,
                "description": "Full arm or full leg complete hair removal wax treatment.",
            },
            {
                "name": "Brazilian Wax",
                "price": Decimal("1200.00"),
                "duration_minutes": 45,
                "description": "Professional hair removal waxing service.",
            },
        ],
    },
    {
        "category": "Lashes",
        "description": "Eyelash enhancement, lash lifts, tints, and extension services.",
        "services": [
            {
                "name": "Eyelash Lift",
                "price": Decimal("500.00"),
                "duration_minutes": 45,
                "description": "Curls and lifts your natural lashes, making them look longer and fuller for 4 to 6 weeks.",
            },
            {
                "name": "Eyelash Lift with Tint",
                "price": Decimal("850.00"),
                "duration_minutes": 60,
                "description": "Achieve effortlessly lifted, darker, and fuller-looking lashes with results lasting up to 4-6 weeks.",
            },
            {
                "name": "Classic Extension",
                "price": Decimal("800.00"),
                "duration_minutes": 90,
                "description": "Our signature 1:1 technique creating a clean, soft, and naturally enhanced look. (+ 200 for Full Classic Extension)",
            },
            {
                "name": "Wet Look Extension",
                "price": Decimal("1150.00"),
                "duration_minutes": 90,
                "description": "Defined, textured lash strands for a fresh mascara effect using our signature 1:1 method.",
            },
            {
                "name": "Lash Refill",
                "price": Decimal("400.00"),
                "duration_minutes": 45,
                "description": "Retouch requires 60% retention; 1-2 refills only—otherwise, new set. 50% of lash rate.",
            },
            {
                "name": "Lash Removal",
                "price": Decimal("250.00"),
                "duration_minutes": 30,
                "description": "This process is designed to gently remove lash extensions without damaging your natural lashes.",
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Loads and synchronizes the Get Nailed service catalog from the menu images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing services before loading.",
        )

    def handle(self, *args, **options):
        clear = options.get("clear", False)
        with transaction.atomic():
            if clear:
                old_service_count = Service.objects.count()
                self.stdout.write(f"Deleting {old_service_count} existing services...")
                Service.objects.all().delete()

                new_cat_names = [group["category"] for group in MENU_DATA]
                old_cats = ServiceCategory.objects.exclude(name__in=new_cat_names)
                old_cat_count = old_cats.count()
                if old_cat_count > 0:
                    self.stdout.write(f"Deleting {old_cat_count} unused categories...")
                    old_cats.delete()

            total_created = 0
            total_updated = 0

            for group in MENU_DATA:
                cat_name = group["category"]
                cat_desc = group["description"]
                category, _ = ServiceCategory.objects.get_or_create(
                    name=cat_name,
                    defaults={"description": cat_desc},
                )
                if category.description != cat_desc:
                    category.description = cat_desc
                    category.save()

                for sdata in group["services"]:
                    service, created = Service.objects.update_or_create(
                        category=category,
                        name=sdata["name"],
                        defaults={
                            "price": sdata["price"],
                            "duration_minutes": sdata["duration_minutes"],
                            "description": sdata["description"],
                            "is_active": True,
                        },
                    )
                    if created:
                        total_created += 1
                    else:
                        total_updated += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully synchronized catalog! Created: {total_created}, Updated: {total_updated}. "
                    f"Total services in database: {Service.objects.count()} across {ServiceCategory.objects.count()} categories."
                )
            )
