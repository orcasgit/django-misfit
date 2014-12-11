from misfitapp.models import MisfitUser

from .base import MisfitTestBase


class TestMisfitModels(MisfitTestBase):
    def test_misfit_user(self):
        """ MisfitUser was already created in base, now test the properties """
        self.assertEqual(self.misfit_user.user, self.user)
        self.assertEqual(self.misfit_user.__str__(), self.username)
        self.assertEqual(self.misfit_user.last_update, None)
        self.assertEqual(self.misfit_user.access_token, self.access_token)
        self.assertEqual(self.misfit_user.misfit_user_id, self.misfit_user_id)
