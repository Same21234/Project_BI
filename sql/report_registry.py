
# ==========================================================
# REPORT REGISTRY
# ==========================================================

from reports.Branchwise_Analysis import render_report as branch_report
from reports.ATS_Analysis import ATS_Analysis
from reports.Monthly_Disbursement import Monthly_Disbursement
from reports.ATS_Disb_MoM import ATS_Disb_MoM
from reports.Vintage_Analysis import render_report as vintage_report
from reports.Cohort_Analysis import render_report as cohort_report


# ==========================================================
# REGISTER ALL REPORTS
# ==========================================================

REPORTS = {

    "🏢 Branch Wise Analysis": {
        "view": "branch_wise_analysis",
        "function": branch_report,
    },

    "🧮 ATS Analysis": {
        "view": "ats_analysis",
        "function": ATS_Analysis,
    },

    "📊 Monthly Disb": {
        "view": "Monthly Disbursement",
        "function": Monthly_Disbursement,
    },

    "📈 ATS_Disb_MoM": {
        "view": "ATS_Disb_MoM",
        "function": ATS_Disb_MoM,
    },

    "🧭 Vintage Analysis": {
        "view": "vintage_analysis",
        "function": vintage_report,
        "uses_internal_filters": True,
    },

    "🧭 Cohort Analysis": {
        "view": "cohort_analysis",
        "function": cohort_report,
        "uses_internal_filters": True,
    },

}